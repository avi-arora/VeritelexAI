"""Resilience primitives: error classification, retry with backoff + jitter,
and a circuit breaker. Used both inside steps (LLM calls) and by the
dispatchers (whole-step retries)."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

from google.api_core import exceptions as gexc

from app.logging_setup import get_logger

log = get_logger(__name__)
T = TypeVar("T")


class StepError(Exception):
    """Base class for errors raised by agents. ``user_message`` is safe to show in the UI."""

    retryable: bool = True

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or "Analysis step failed"


class RetryableStepError(StepError):
    retryable = True


class PermanentStepError(StepError):
    retryable = False


class SchemaError(RetryableStepError):
    """Model output did not match the schema even after a repair attempt."""


NOT_ENABLED_DETAIL = "Not enabled in Model Garden for this project"


class UnavailableError(PermanentStepError):
    """Every model that could serve the call is unavailable to this project (not enabled in
    Model Garden, or no access). A configuration state, not a fault: retrying cannot help."""

    def __init__(self, message: str, user_message: str | None = None, detail: str = NOT_ENABLED_DETAIL):
        super().__init__(message, user_message)
        self.detail = detail
        """Why, in words the UI shows next to the member (e.g. "Not enabled in Model Garden for this project")."""


class LeaseHeldError(Exception):
    """Another worker currently holds the lease for this step."""


class CircuitOpenError(RetryableStepError):
    pass


_RETRYABLE_HTTP = {408, 409, 429, 500, 502, 503, 504}
_RETRYABLE_GCP = (
    gexc.TooManyRequests, gexc.ServiceUnavailable, gexc.DeadlineExceeded, gexc.InternalServerError,
    gexc.BadGateway, gexc.GatewayTimeout, gexc.Aborted, gexc.RetryError,
)
_RETRYABLE_NAMES = {
    # httpx / aiohttp transport errors, google-genai server errors
    "ServerError", "ConnectError", "ReadTimeout", "RemoteProtocolError", "ReadError", "WriteError",
    # requests / urllib3 (used by google-cloud-storage) and google-auth token refresh
    "ConnectionError", "ChunkedEncodingError", "Timeout", "ProtocolError", "IncompleteRead", "TransportError",
}


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, StepError):
        return exc.retryable
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, _RETRYABLE_GCP):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _RETRYABLE_HTTP:
        return True
    # Matched by name across the MRO so these libraries stay optional imports and subclasses
    # (e.g. requests' ConnectTimeout, a ConnectionError) are covered too.
    return any(c.__name__ in _RETRYABLE_NAMES for c in type(exc).__mro__)


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 60.0) -> float:
    """Full-jitter exponential backoff (AWS architecture blog), attempt is 1-based."""
    return random.uniform(0, min(cap, base * (2 ** (attempt - 1))))


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base: float = 2.0,
    cap: float = 30.0,
    what: str = "call",
) -> T:
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            if not is_retryable(exc) or attempt == attempts:
                raise
            delay = backoff_delay(attempt, base, cap)
            log.warning(
                "%s failed (attempt %d/%d), retrying in %.1fs: %s: %s",
                what, attempt, attempts, delay, type(exc).__name__, str(exc)[:300],
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable") from last


@dataclass
class CircuitBreaker:
    """Classic three-state breaker. Opens after ``threshold`` consecutive
    failures; after ``cooldown`` seconds lets a single probe through."""

    name: str
    threshold: int
    cooldown: float
    _failures: int = 0
    _opened_at: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        return "half-open" if time.monotonic() - self._opened_at >= self.cooldown else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            if self._opened_at is None:
                log.warning("circuit %s opened after %d failures", self.name, self._failures)
            self._opened_at = time.monotonic()
