"""Model council: one facade over every member's model chain.

Resilience for each member call, outermost first:

1. Fallback chain: each member lists models in order of preference (e.g. Opus 5.5 → Sonnet 5.5).
2. Availability memory: a model that answers 404/403 (not enabled in Model Garden) is skipped
   for ``council_unavailable_ttl_s``, then tried again, so enabling it needs no restart.
3. Circuit breaker for each model: repeated transient failures stop traffic for a cooldown.
4. Retries with full-jitter backoff that honour ``Retry-After`` on 429/503.
5. Concurrency semaphore and sliding-window rate limiter for each member, sized to the
   project's quota, so the council does not cause its own 429s.
6. JSON validation against the Pydantic schema, with one repair round trip.

Every member is reached through Google Cloud with Application Default Credentials. Members
never use their own web-search tools: law comes only from the pipeline's authorities, which are
grounded with Google Search and verified.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import CouncilMember, Settings
from app.harness.llm import GeminiLLM, Grounding, LLMResult, parse_json
from app.harness.providers import (
    NOT_ENABLED,
    ModelUnavailable,
    RateLimited,
    RateLimiter,
    TextResult,
    VertexRest,
    unavailable_reason,
)
from app.harness.resilience import (
    CircuitBreaker,
    PermanentStepError,
    RetryableStepError,
    SchemaError,
    UnavailableError,
    backoff_delay,
    is_retryable,
)
from app.logging_setup import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


def _short(exc: BaseException, n: int = 240) -> str:
    return f"{type(exc).__name__}: {exc}"[:n]


def estimate_tokens(chars: int) -> int:
    """Conservative token estimate for rate limiting (legal text averages ~4 chars per token)."""
    return chars // 3 + 1


class CouncilLLM:
    def __init__(self, settings: Settings, gemini: GeminiLLM, rest: VertexRest | None = None):
        self._s = settings
        self._gemini = gemini
        self._rest = rest or VertexRest(settings)
        self.members: dict[str, CouncilMember] = {m.id: m for m in settings.council_members if m.enabled}
        self._sems = {m.id: asyncio.Semaphore(max(1, m.concurrency)) for m in self.members.values()}
        self._limits = {m.id: RateLimiter(m.rpm, m.input_tpm, m.output_tpm) for m in self.members.values()}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._unavailable: dict[str, tuple[float, str]] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._probe_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------ membership
    def ids(self) -> list[str]:
        return list(self.members) if self._s.council_enabled else []

    async def aclose(self) -> None:
        await self._rest.aclose()

    def member(self, member_id: str) -> CouncilMember:
        m = self.members.get(member_id)
        if m is None:
            raise PermanentStepError(f"unknown council member {member_id!r}", "This council member is no longer configured")
        return m

    def chair_order(self, prefer: Iterable[str] = ()) -> list[str]:
        """Members in chair order, with ``prefer`` (e.g. the members that answered) first."""
        base = [m for m in self._s.council_chair if m in self.members] + [m for m in self.members if m not in self._s.council_chair]
        first = set(prefer)
        return [m for m in base if m in first] + [m for m in base if m not in first]

    def console_url(self, m: CouncilMember) -> str:
        return m.console_url.replace("{project}", self._s.project_id)

    def _breaker(self, model: str) -> CircuitBreaker:
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker(model, self._s.breaker_failures, self._s.breaker_cooldown_s)
        return self._breakers[model]

    # ------------------------------------------------------------ status
    def _note(self, m: CouncilMember, status: str, model: str | None, detail: str = "") -> None:
        self._status[m.id] = {"status": status, "activeModel": model, "detail": detail, "checkedAt": datetime.now(UTC), "at": time.monotonic()}

    def _note_ok(self, m: CouncilMember, model: str) -> None:
        if model == m.models[0]:
            self._note(m, "ready", model)
        else:
            self._note(m, "fallback", model, f"{m.models[0]} is unavailable; {model} answered instead")

    def status(self, member_id: str) -> dict[str, Any]:
        cur = self._status.get(member_id)
        if not cur or time.monotonic() - cur["at"] > self._s.council_status_ttl_s:
            return {"status": "unknown", "activeModel": None, "detail": "Not checked yet", "checkedAt": None}
        return cur

    async def probe(self, member_id: str, *, force: bool = False) -> dict[str, Any]:
        """Check (and cache) whether a member can answer: the first model that responds wins."""
        m = self.member(member_id)
        lock = self._probe_locks.setdefault(member_id, asyncio.Lock())
        async with lock:
            cur = self.status(member_id)
            if cur["status"] != "unknown" and not force:
                return cur
            notes: list[str] = []
            errored = False
            for i, model in enumerate(m.models):
                try:
                    await asyncio.wait_for(self._ping(m, model), timeout=90)
                except RateLimited:
                    pass  # the model exists and is enabled; it is only busy right now
                except ModelUnavailable as exc:
                    self._unavailable[model] = (time.monotonic() + self._s.council_unavailable_ttl_s, exc.reason)
                    notes.append(f"{model}: {exc.reason}")
                    log.info("probe: %s %s unavailable: %s", m.id, model, str(exc)[:200])
                    continue
                except Exception as exc:  # noqa: BLE001 - reported, never raised
                    errored = True
                    notes.append(f"{model}: {_short(exc, 160)}")
                    continue
                self._unavailable.pop(model, None)
                self._breaker(model).success()
                if i == 0:
                    self._note(m, "ready", model)
                else:
                    self._note(m, "fallback", model, "; ".join(notes) + f"; using {model}")
                return self.status(member_id)
            self._note(m, "error" if errored else "unavailable", None, "; ".join(notes))
            return self.status(member_id)

    async def _ping(self, m: CouncilMember, model: str) -> None:
        if m.provider != "gemini":
            await self._rest.ping(m.provider, model, m.location)
            return
        try:
            await self._gemini.raw_ping(model)
        except Exception as exc:  # noqa: BLE001 - translated to the provider-neutral errors
            code = getattr(exc, "code", None)
            if code in (403, 404):
                raise ModelUnavailable(str(exc)[:300], unavailable_reason(str(exc))) from exc
            if code == 429:
                raise RateLimited(str(exc)[:300]) from exc
            raise

    # ------------------------------------------------------------ generation
    async def generate(
        self, member_id: str, *, schema: type[T], system: str, contents: list[str],
        temperature: float = 0.2, max_output_tokens: int | None = None,
    ) -> LLMResult[T]:
        """Structured output from one member, down its fallback chain.

        Raises ``UnavailableError`` when none of the member's models is enabled for the project,
        ``PermanentStepError`` when every model rejected the request, otherwise ``RetryableStepError``.
        """
        m = self.member(member_id)
        max_out = min(max_output_tokens or m.max_output_tokens, m.max_output_tokens)
        if m.provider == "gemini":
            async with self._sems[m.id]:
                try:
                    res = await self._gemini.generate(
                        schema=schema, system=system, contents=list(contents), tier="pro",
                        temperature=temperature, max_output_tokens=max_out, models=m.models,
                    )
                except UnavailableError as exc:
                    self._note(m, "unavailable", None, str(exc)[:300])
                    raise
            self._note_ok(m, res.model)
            return res

        errors: list[str] = []
        reasons: list[str] = []
        only_unavailable = True
        all_permanent = True
        for model in m.models:
            mark = self._unavailable.get(model)
            if mark and mark[0] > time.monotonic():
                errors.append(f"{model}: {mark[1]}")
                reasons.append(mark[1])
                continue
            breaker = self._breaker(model)
            if not breaker.allow():
                errors.append(f"{model}: circuit open")
                only_unavailable = all_permanent = False
                continue
            try:
                res = await self._retry(
                    lambda mo=model: self._validated(m, mo, schema, system, contents, temperature, max_out),
                    what=f"council[{m.id}:{model}]",
                )
            except ModelUnavailable as exc:
                self._unavailable[model] = (time.monotonic() + self._s.council_unavailable_ttl_s, exc.reason)
                errors.append(f"{model}: {exc.reason}")
                reasons.append(exc.reason)
                log.warning("council %s: %s unavailable, falling back: %s", m.id, model, str(exc)[:300])
            except PermanentStepError as exc:
                only_unavailable = False
                errors.append(f"{model}: {exc}"[:300])
                log.warning("council %s: %s rejected the request: %s", m.id, model, exc)
            except Exception as exc:  # noqa: BLE001
                if not is_retryable(exc):
                    raise
                only_unavailable = all_permanent = False
                breaker.failure()
                errors.append(f"{model}: {_short(exc, 300)}")
                log.warning("council %s: %s failed, trying fallback: %s", m.id, model, exc)
            else:
                breaker.success()
                self._unavailable.pop(model, None)
                self._note_ok(m, model)
                return res
        detail = "; ".join(errors)
        if only_unavailable and errors:
            self._note(m, "unavailable", None, detail)
            why = sorted({r for r in reasons if r != NOT_ENABLED})
            if why:
                ui = "; ".join(why)
                ui = ui[0].upper() + ui[1:]
                raise UnavailableError(f"{m.name} is not available: {detail}", user_message=f"{m.name}: {ui}", detail=ui)
            raise UnavailableError(f"{m.name} is not available: {detail}", user_message=f"{m.name} is not enabled for this project")
        if all_permanent and errors:
            raise PermanentStepError(f"{m.name}: every model rejected the request: {detail}", f"{m.name} could not answer")
        raise RetryableStepError(f"{m.name}: all models failed: {detail}", f"{m.name} is temporarily unavailable — retrying")

    async def _retry(self, fn: Callable[[], Awaitable[R]], *, what: str) -> R:
        attempts = max(1, self._s.llm_call_attempts)
        for attempt in range(1, attempts + 1):
            try:
                return await fn()
            except Exception as exc:  # noqa: BLE001 - classified below
                if not is_retryable(exc) or attempt == attempts:
                    raise
                delay = backoff_delay(attempt, 2.0, 30.0)
                retry_after = getattr(exc, "retry_after", None)
                if retry_after:
                    delay = max(delay, min(float(retry_after), 60.0))
                log.warning("%s failed (attempt %d/%d), retrying in %.1fs: %s", what, attempt, attempts, delay, _short(exc, 300))
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _validated(
        self, m: CouncilMember, model: str, schema: type[T], system: str, contents: list[str],
        temperature: float, max_out: int,
    ) -> LLMResult[T]:
        sys_text = (
            f"{system}\n\nRespond with ONLY one JSON object (no prose before or after it, no code fences) that "
            f"matches this JSON schema:\n{json.dumps(schema.model_json_schema())}"
        )
        first = await self._call(m, model, sys_text, contents, None, temperature, max_out)
        try:
            return LLMResult(data=parse_json(first.text, schema), model=model, usage=first.usage, grounding=Grounding())
        except (ValidationError, ValueError) as exc:
            why = (
                "was cut off before it finished" if first.truncated
                else f"did not match the required JSON schema. Error:\n{str(exc)[:2000]}"
            )
            log.info("council %s:%s schema repair: %s", m.id, model, why[:200])
        history = [
            {"role": "assistant", "content": first.text[:200_000] or "(no answer)"},
            {"role": "user", "content": f"Your previous answer {why}\nReturn ONLY the corrected, complete JSON object. Be more concise if needed."},
        ]
        second = await self._call(m, model, sys_text, contents, history, temperature, max_out)
        usage = {k: first.usage.get(k, 0) + second.usage.get(k, 0) for k in {*first.usage, *second.usage}}
        try:
            data = parse_json(second.text, schema)
        except (ValidationError, ValueError) as exc:
            raise SchemaError(f"{schema.__name__} from {model} invalid after repair: {str(exc)[:400]}") from exc
        return LLMResult(data=data, model=model, usage=usage, grounding=Grounding())

    async def _call(
        self, m: CouncilMember, model: str, system: str, contents: list[str], history: list[dict[str, str]] | None,
        temperature: float, max_out: int,
    ) -> TextResult:
        chars = len(system) + sum(len(c) for c in contents) + sum(len(h["content"]) for h in history or [])
        async with self._sems[m.id]:
            waited = await self._limits[m.id].acquire(estimate_tokens(chars))
            if waited > 1:
                log.info("council %s waited %.0fs for its rate-limit budget", m.id, waited)
            res = await asyncio.wait_for(
                self._rest.call(m.provider, model, m.location, system=system, blocks=list(contents), history=history,
                                max_tokens=max_out, temperature=temperature, json_mode=m.json_mode),
                timeout=self._s.llm_call_timeout_s + 30,
            )
            self._limits[m.id].record_output(res.usage.get("output", 0))
        return res
