"""Gemini (Vertex AI) client wrapper used by every agent.

Guarantees for callers:
  * Structured output validated against a Pydantic schema (one repair round-trip).
  * Per-call timeout and in-call retries for transient errors.
  * Model fallback chain per tier with a circuit breaker per model.
  * Process-wide concurrency cap to protect quota.
  * Grounding metadata (search queries + sources) surfaced when Google Search is used.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Protocol, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.agents.schemas import SourceRef
from app.config import Settings
from app.harness.resilience import (
    CircuitBreaker,
    PermanentStepError,
    RetryableStepError,
    SchemaError,
    UnavailableError,
    is_retryable,
    retry_async,
)
from app.logging_setup import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")
Tier = Literal["pro", "flash"]


@dataclass
class Grounding:
    queries: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class LLMResult(Generic[T]):
    data: T
    model: str
    usage: dict[str, int]
    grounding: Grounding


class LLM(Protocol):
    async def generate(
        self,
        *,
        schema: type[T],
        system: str,
        contents: list[Any],
        tier: Tier = "flash",
        search: bool = False,
        temperature: float = 0.2,
        max_output_tokens: int = 32_768,
    ) -> LLMResult[T]: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str, schema: type[T]) -> T:
    cleaned = _FENCE.sub("", (text or "").strip())
    if not cleaned.startswith(("{", "[")):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return schema.model_validate(json.loads(cleaned))


class _ModelUnavailable(Exception):
    pass


@dataclass
class _Research:
    text: str
    grounding: Grounding
    usage: dict[str, int]
    supports: list[tuple[int, list[int]]]
    """(segment end byte offset, grounding chunk indices) for inline citation markers."""


class GeminiLLM:
    def __init__(self, settings: Settings):
        self._s = settings
        self._client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.vertex_location,
            http_options=types.HttpOptions(timeout=settings.llm_call_timeout_s * 1000),
        )
        self._sem = asyncio.Semaphore(settings.llm_concurrency)
        self._breakers: dict[str, CircuitBreaker] = {}
        self._unavailable: set[str] = set()

    def _breaker(self, model: str) -> CircuitBreaker:
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker(model, self._s.breaker_failures, self._s.breaker_cooldown_s)
        return self._breakers[model]

    async def generate(
        self,
        *,
        schema: type[T],
        system: str,
        contents: list[Any],
        tier: Tier = "flash",
        search: bool = False,
        temperature: float = 0.2,
        max_output_tokens: int = 32_768,
        models: list[str] | None = None,
    ) -> LLMResult[T]:
        """``models`` overrides the tier's fallback chain (used by the council's Gemini member)."""
        if not search:
            return await self._chain(
                tier, lambda m: self._call_validated(m, schema, system, contents, False, temperature, max_output_tokens), models
            )
        # Two-phase grounding. With a JSON response Gemini still searches but attaches no
        # grounding chunks (chunks are tied to cited prose), so: (1) grounded research in prose,
        # collecting sources + citation supports; (2) structure those notes into the schema
        # without tools. Sources returned to the caller come only from phase 1.
        research = await self._chain(tier, lambda m: self._research(m, system, contents, temperature), models)
        notes = _render_research(research)
        system2 = (
            f"{system}\n\nThe web research for this task has already been done with Google Search and is given below "
            "as RESEARCH NOTES with numbered SOURCES. Use ONLY those notes for external material. Whenever a URL is "
            "required, copy the exact URL of the supporting source from the SOURCES list. Never cite anything that is "
            "not supported by the notes."
        )
        res = await self._chain(
            tier,
            lambda m: self._call_validated(m, schema, system2, [*contents, notes], False, temperature, max_output_tokens),
            models,
        )
        res.grounding = research.grounding
        res.usage = {k: res.usage.get(k, 0) + research.usage.get(k, 0) for k in {*res.usage, *research.usage}}
        return res

    async def raw_ping(self, model: str) -> None:
        """Smallest real call to ``model``; raises the SDK error unchanged (status in ``exc.code``)."""
        config = types.GenerateContentConfig(max_output_tokens=256)
        await asyncio.wait_for(
            self._client.aio.models.generate_content(model=model, contents="Reply with the single word OK.", config=config),
            timeout=60,
        )

    async def _chain(self, tier: Tier, fn: Callable[[str], Awaitable[R]], models: list[str] | None = None) -> R:
        """Run ``fn(model)`` down the fallback chain with retries and per-model breakers."""
        chain = models or (self._s.model_pro if tier == "pro" else self._s.model_flash)
        errors: list[str] = []
        all_permanent = True
        all_unavailable = True
        for model in chain:
            if model in self._unavailable:
                errors.append(f"{model}: unavailable")
                continue
            breaker = self._breaker(model)
            if not breaker.allow():
                errors.append(f"{model}: circuit open")
                all_permanent = all_unavailable = False
                continue
            try:
                result = await retry_async(lambda m=model: fn(m), attempts=self._s.llm_call_attempts, what=f"gemini[{model}]")
                breaker.success()
                return result
            except _ModelUnavailable as exc:
                log.warning("model %s unavailable, falling back: %s", model, exc)
                self._unavailable.add(model)
                errors.append(f"{model}: unavailable")
            except PermanentStepError as exc:
                all_unavailable = False
                errors.append(f"{model}: {exc}"[:300])
                log.warning("model %s rejected the request, trying fallback: %s", model, exc)
            except Exception as exc:  # noqa: BLE001
                if not is_retryable(exc):
                    raise
                all_permanent = all_unavailable = False
                breaker.failure()
                errors.append(f"{model}: {type(exc).__name__}: {exc}"[:300])
                log.warning("model %s failed, trying fallback: %s", model, exc)
        if all_unavailable and errors:
            raise UnavailableError("No model in the chain is available: " + "; ".join(errors),
                                   user_message="The AI model is not enabled for this project")
        if all_permanent and errors:
            raise PermanentStepError("All models rejected the request: " + "; ".join(errors))
        raise RetryableStepError(
            "All models in the %s chain failed: %s" % (tier, "; ".join(errors)),
            user_message="The AI service is temporarily unavailable — it will be retried automatically",
        )

    async def _research(self, model: str, system: str, contents: list[Any], temperature: float) -> _Research:
        config = types.GenerateContentConfig(
            system_instruction=(
                f"{system}\n\nFor now, do the research only: search Google and write concise research notes in prose "
                "covering every authority you find (name, citation, court, date, and what it decides), with sources."
            ),
            temperature=temperature,
            max_output_tokens=16_384,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        resp = await self._generate(model, contents, config)
        return _Research(text=_text_of(resp), grounding=_grounding_of(resp), usage=_usage_of(resp), supports=_supports_of(resp))

    async def _call_validated(
        self, model: str, schema: type[T], system: str, contents: list[Any], search: bool,
        temperature: float, max_output_tokens: int,
    ) -> LLMResult[T]:
        resp = await self._call(model, schema, system, contents, search, temperature, max_output_tokens)
        text = _text_of(resp)
        try:
            data = parse_json(text, schema)
        except (ValidationError, ValueError) as exc:
            log.info("schema repair for %s: %s", schema.__name__, str(exc)[:300])
            repair = [
                *contents,
                types.Content(role="model", parts=[types.Part.from_text(text=text[:200_000] or "(empty)")]),
                "Your previous answer did not match the required JSON schema. Error:\n"
                f"{str(exc)[:2000]}\nReturn ONLY the corrected JSON object.",
            ]
            resp = await self._call(model, schema, system, repair, search, temperature, max_output_tokens)
            text = _text_of(resp)
            try:
                data = parse_json(text, schema)
            except (ValidationError, ValueError) as exc2:
                raise SchemaError(f"{schema.__name__} invalid after repair: {str(exc2)[:500]}") from exc2
        return LLMResult(data=data, model=model, usage=_usage_of(resp), grounding=_grounding_of(resp))

    async def _call(
        self, model: str, schema: type[T], system: str, contents: list[Any], search: bool,
        temperature: float, max_output_tokens: int,
    ) -> types.GenerateContentResponse:
        # Gemini 3 supports structured output together with built-in tools; older
        # models get the schema in the prompt instead and are validated the same way.
        schema_with_tools = model.startswith("gemini-3")
        use_schema = (not search) or schema_with_tools
        sys_text = system
        if not use_schema:
            sys_text += "\n\nRespond with ONLY a JSON object matching this JSON schema:\n" + json.dumps(
                schema.model_json_schema()
            )
        config = types.GenerateContentConfig(
            system_instruction=sys_text,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if use_schema else None,
            response_schema=schema if use_schema else None,
            tools=[types.Tool(google_search=types.GoogleSearch())] if search else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return await self._generate(model, contents, config)

    async def _generate(self, model: str, contents: list[Any], config: types.GenerateContentConfig) -> types.GenerateContentResponse:
        async with self._sem:
            try:
                resp = await asyncio.wait_for(
                    self._client.aio.models.generate_content(model=model, contents=contents, config=config),
                    timeout=self._s.llm_call_timeout_s + 15,
                )
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "code", None)
                msg = str(exc).lower()
                if code == 404 or ("not found" in msg and "model" in msg):
                    raise _ModelUnavailable(str(exc)[:300]) from exc
                if code == 400:
                    raise PermanentStepError(f"Gemini rejected the request: {str(exc)[:500]}") from exc
                raise
        cand = (resp.candidates or [None])[0]
        reason = getattr(cand, "finish_reason", None) if cand else None
        if cand is None or (reason and str(reason).endswith(("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"))):
            raise RetryableStepError(f"Gemini returned no usable candidate (finish_reason={reason})")
        return resp


def _text_of(resp: types.GenerateContentResponse) -> str:
    try:
        return resp.text or ""
    except Exception:  # noqa: BLE001 - .text raises if parts are non-text
        return ""


def _usage_of(resp: types.GenerateContentResponse) -> dict[str, int]:
    u = resp.usage_metadata
    if not u:
        return {}
    return {
        "prompt": u.prompt_token_count or 0,
        "output": u.candidates_token_count or 0,
        "total": u.total_token_count or 0,
    }


def _grounding_of(resp: types.GenerateContentResponse) -> Grounding:
    g = Grounding()
    cand = (resp.candidates or [None])[0]
    meta = getattr(cand, "grounding_metadata", None) if cand else None
    if not meta:
        return g
    g.queries = list(meta.web_search_queries or [])
    seen: set[str] = set()
    for chunk in meta.grounding_chunks or []:
        web = getattr(chunk, "web", None)
        if web and web.uri and web.uri not in seen:
            seen.add(web.uri)
            g.sources.append(SourceRef(uri=web.uri, title=web.title or "", domain=web.domain or ""))
    return g


def _supports_of(resp: types.GenerateContentResponse) -> list[tuple[int, list[int]]]:
    """Citation supports with chunk indices re-mapped to positions in ``_grounding_of(resp).sources``.

    Raw chunk indices point into ``grounding_chunks`` which may repeat a URI; sources are de-duplicated
    in first-seen order, so each chunk index is translated through its URI.
    """
    cand = (resp.candidates or [None])[0]
    meta = getattr(cand, "grounding_metadata", None) if cand else None
    if not meta:
        return []
    pos: dict[str, int] = {}
    chunk_to_src: dict[int, int] = {}
    for ci, chunk in enumerate(meta.grounding_chunks or []):
        web = getattr(chunk, "web", None)
        if web and web.uri:
            chunk_to_src[ci] = pos.setdefault(web.uri, len(pos))
    out: list[tuple[int, list[int]]] = []
    for sup in meta.grounding_supports or []:
        seg = sup.segment
        idxs = sorted({chunk_to_src[i] for i in (sup.grounding_chunk_indices or []) if i in chunk_to_src})
        if seg is not None and seg.end_index is not None and idxs:
            out.append((int(seg.end_index), idxs))
    return out


def _render_research(r: _Research) -> str:
    """Research notes with inline [n] markers (segment offsets are UTF-8 byte offsets) and a numbered source list."""
    text = r.text.encode("utf-8")
    for end, idxs in sorted(r.supports, key=lambda x: -x[0]):
        marks = "".join(f"[{i + 1}]" for i in idxs if i < len(r.grounding.sources))
        if marks and 0 <= end <= len(text):
            text = text[:end] + marks.encode() + text[end:]
    sources = "\n".join(
        f"[{i + 1}] {s.title or s.domain} ({s.domain or 'web'}) — {s.uri}" for i, s in enumerate(r.grounding.sources)
    ) or "(no sources returned)"
    return f"RESEARCH NOTES (Google Search)\n{text.decode('utf-8', errors='ignore')}\n\nSOURCES\n{sources}"
