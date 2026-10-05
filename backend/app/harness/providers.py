"""REST clients for council members served from Google Cloud Agent Platform (Vertex AI).

* Anthropic Claude — ``publishers/anthropic/models/{model}:rawPredict`` (Messages API body).
* OpenAI-compatible partner models (xAI Grok) — ``endpoints/openapi/chat/completions``.

Both authenticate with Application Default Credentials: no third-party API keys exist anywhere.
They return plain text; JSON validation, fallback chains and breakers live in
:mod:`app.harness.council`. Errors are classified for the caller:

* ``ModelUnavailable``   — 404, or 403: the model is not enabled for the project (Model Garden terms
  not accepted) or the caller lacks access. Skipped for a while, then tried again.
* ``BadRequest``         — any other 4xx: the request is wrong; retrying the same call cannot help.
* ``RateLimited``        — 429/503 (retryable), carrying ``Retry-After`` when the server sends one.
* ``RetryableStepError`` — 401 (token refreshed), 408/409/5xx; transport errors are retryable by type.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import google.auth
import google.auth.transport.requests
import httpx

from app.config import Settings
from app.harness.resilience import PermanentStepError, RetryableStepError
from app.logging_setup import get_logger

log = get_logger(__name__)
_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
ANTHROPIC_VERSION = "vertex-2023-10-16"


NOT_ENABLED = "not enabled for this project"


class ModelUnavailable(Exception):
    """The model is not enabled for this project or not served in this location, or the caller lacks access."""

    def __init__(self, message: str, reason: str = NOT_ENABLED):
        super().__init__(message)
        self.reason = reason


def unavailable_reason(body: str) -> str:
    """Short reason for a 403/404 from Agent Platform. Not every 403 means "enable it in Model Garden"."""
    low = body.lower()
    if "aiplatform.endpoints.predict" in low or "iam_permission_denied" in low:
        return "no permission to call it (the caller needs roles/aiplatform.user)"
    if "organization policy" in low or "allowedmodels" in low:
        return "blocked by an organization policy"
    if "service_disabled" in low or "has not been used in project" in low:
        return "the Vertex AI API is disabled for this project"
    return NOT_ENABLED


class BadRequest(PermanentStepError):
    def __init__(self, message: str, body: str):
        super().__init__(message, "The AI service rejected the request")
        self.body = body


class RateLimited(RetryableStepError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message, "The AI service is busy — it will be retried automatically")
        self.retry_after = retry_after


@dataclass
class TextResult:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    """The model stopped at ``max_tokens``: the text is incomplete."""


def host(location: str) -> str:
    """Agent Platform endpoint for a location: global, a multi-region (us/eu) or a region."""
    if location == "global":
        return "https://aiplatform.googleapis.com"
    if location in ("us", "eu"):
        return f"https://aiplatform.{location}.rep.googleapis.com"
    return f"https://{location}-aiplatform.googleapis.com"


class TokenSource:
    """Thread-safe ADC access-token cache; google-auth refreshes ~4 minutes before expiry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._creds: Any = None

    def _token(self, force: bool) -> str:
        with self._lock:
            if self._creds is None:
                self._creds, _ = google.auth.default(scopes=_SCOPES)
            if force or not self._creds.valid:
                self._creds.refresh(google.auth.transport.requests.Request())
            return str(self._creds.token)

    async def token(self, force: bool = False) -> str:
        return await asyncio.to_thread(self._token, force)


class RateLimiter:
    """Sliding-window (60 s) limiter for requests, input tokens and output tokens.

    Input tokens are estimated before the call; output tokens are recorded after it. A single
    call larger than the window budget is still let through when the window is empty, so an
    oversized request cannot deadlock (the server's own quota decides then).
    """

    WINDOW = 60.0

    def __init__(self, rpm: int = 0, input_tpm: int = 0, output_tpm: int = 0):
        self.rpm, self.input_tpm, self.output_tpm = rpm, input_tpm, output_tpm
        self._req: deque[tuple[float, int]] = deque()
        self._out: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    @property
    def limited(self) -> bool:
        return bool(self.rpm or self.input_tpm or self.output_tpm)

    def _prune(self, now: float) -> None:
        for d in (self._req, self._out):
            while d and now - d[0][0] >= self.WINDOW:
                d.popleft()

    def _wait_needed(self, now: float, est: int) -> float:
        waits: list[float] = []
        if self.rpm and len(self._req) >= self.rpm:
            waits.append(self._req[0][0] + self.WINDOW - now)
        if self.input_tpm and self._req and sum(n for _, n in self._req) + est > self.input_tpm:
            waits.append(self._req[0][0] + self.WINDOW - now)
        if self.output_tpm and self._out and sum(n for _, n in self._out) >= self.output_tpm:
            waits.append(self._out[0][0] + self.WINDOW - now)
        return max(waits) if waits else 0.0

    async def acquire(self, est_input_tokens: int) -> float:
        """Wait for budget, then reserve it. Returns the seconds spent waiting."""
        if not self.limited:
            return 0.0
        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)
                wait = self._wait_needed(now, est_input_tokens)
                if wait <= 0:
                    self._req.append((now, est_input_tokens))
                    return waited
            wait = min(max(wait, 0.05), self.WINDOW)
            waited += wait
            await asyncio.sleep(wait)

    def record_output(self, tokens: int) -> None:
        if self.output_tpm and tokens > 0:
            self._out.append((time.monotonic(), tokens))


def _classify(resp: httpx.Response, model: str) -> Exception:
    code = resp.status_code
    body = resp.text[:2000]
    msg = f"{model}: HTTP {code}: {body[:400]}"
    if code in (403, 404):
        return ModelUnavailable(msg, unavailable_reason(body))
    if code in (429, 503):
        retry_after: float | None = None
        try:
            retry_after = float(resp.headers.get("retry-after", ""))
        except ValueError:
            pass
        return RateLimited(msg, retry_after)
    if code in (401, 408, 409) or code >= 500:
        return RetryableStepError(msg, "The AI service is temporarily unavailable — it will be retried automatically")
    return BadRequest(msg, body)


class VertexRest:
    """Raw REST calls to partner models on Agent Platform. One pooled HTTP client per process."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, tokens: TokenSource | None = None):
        self._s = settings
        self._tokens = tokens or TokenSource()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_call_timeout_s, connect=20.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        # Parameters a model refused once (HTTP 400) are not sent to it again.
        self._no_temperature: set[str] = set()
        self._no_json_mode: set[str] = set()

    async def _post(self, url: str, body: dict[str, Any], model: str) -> dict[str, Any]:
        token = await self._tokens.token()
        resp = await self._client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            await self._tokens.token(force=True)
        if resp.status_code >= 400:
            raise _classify(resp, model)
        try:
            return resp.json()
        except ValueError as exc:
            raise RetryableStepError(f"{model}: response was not JSON") from exc

    async def call(
        self, provider: str, model: str, location: str, *, system: str, blocks: list[str],
        history: list[dict[str, str]] | None = None, max_tokens: int, temperature: float | None, json_mode: bool = True,
    ) -> TextResult:
        if provider == "anthropic":
            return await self.anthropic(model, location, system=system, blocks=blocks, history=history,
                                        max_tokens=max_tokens, temperature=temperature)
        if provider == "openai":
            return await self.openai(model, location, system=system, blocks=blocks, history=history,
                                     max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)
        raise PermanentStepError(f"unknown provider {provider}")

    # ------------------------------------------------------------------ Claude
    async def anthropic(
        self, model: str, location: str, *, system: str, blocks: list[str], history: list[dict[str, str]] | None,
        max_tokens: int, temperature: float | None,
    ) -> TextResult:
        url = f"{host(location)}/v1/projects/{self._s.project_id}/locations/{location}/publishers/anthropic/models/{model}:rawPredict"
        content: list[dict[str, Any]] = []
        for i, text in enumerate(blocks):
            block: dict[str, Any] = {"type": "text", "text": text}
            # The record is the large, repeated prefix (pre-analysis, then every question): cache it.
            if i == 0 and len(blocks) > 1 and len(text) > 4000:
                block["cache_control"] = {"type": "ephemeral"}
            content.append(block)
        body: dict[str, Any] = {
            "anthropic_version": ANTHROPIC_VERSION, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": content}, *(history or [])],
        }
        # No ``thinking`` parameter: each model uses its default (newer models cannot disable it).
        if temperature is not None and model not in self._no_temperature:
            body["temperature"] = temperature
        try:
            data = await self._post(url, body, model)
        except BadRequest as exc:
            if "temperature" in body and "temperature" in exc.body.lower():
                self._no_temperature.add(model)
                body.pop("temperature")
                data = await self._post(url, body, model)
            else:
                raise
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
        u = data.get("usage") or {}
        prompt = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        out = int(u.get("output_tokens") or 0)
        return TextResult(text=text, model=model, usage={"prompt": prompt, "output": out, "total": prompt + out},
                          truncated=data.get("stop_reason") == "max_tokens")

    # ------------------------------------------------------------------ OpenAI-compatible (Grok)
    async def openai(
        self, model: str, location: str, *, system: str, blocks: list[str], history: list[dict[str, str]] | None,
        max_tokens: int, temperature: float | None, json_mode: bool,
    ) -> TextResult:
        url = f"{host(location)}/v1/projects/{self._s.project_id}/locations/{location}/endpoints/openapi/chat/completions"
        body: dict[str, Any] = {
            "model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(blocks)}, *(history or [])],
        }
        if temperature is not None and model not in self._no_temperature:
            body["temperature"] = temperature
        if json_mode and model not in self._no_json_mode:
            body["response_format"] = {"type": "json_object"}
        data: dict[str, Any] | None = None
        for _ in range(3):
            try:
                data = await self._post(url, body, model)
                break
            except BadRequest as exc:
                low = exc.body.lower()
                if "response_format" in body and ("response_format" in low or "json" in low):
                    self._no_json_mode.add(model)
                    body.pop("response_format")
                elif "temperature" in body and "temperature" in low:
                    self._no_temperature.add(model)
                    body.pop("temperature")
                else:
                    raise
        if data is None:
            raise PermanentStepError(f"{model}: request rejected after removing optional parameters")
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if isinstance(content, list):  # content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        # ``reasoning_content`` (if any) is deliberately ignored: only the answer is used.
        u = data.get("usage") or {}
        prompt, out = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        return TextResult(text=str(content), model=model, usage={"prompt": prompt, "output": out, "total": prompt + out},
                          truncated=choice.get("finish_reason") == "length")

    async def ping(self, provider: str, model: str, location: str) -> None:
        """Cheapest real call that proves the model is enabled and reachable."""
        await self.call(provider, model, location, system="Reply with the single word OK.", blocks=["ping"],
                        max_tokens=1024, temperature=None, json_mode=False)

    async def aclose(self) -> None:
        await self._client.aclose()
