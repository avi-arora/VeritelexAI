"""Structured JSON logging compatible with Cloud Logging.

Context (case_id / run_id / step_id / agent) is carried in a ContextVar so
every log line emitted while a step runs is automatically correlated.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

_ctx: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_ctx", default={})


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = _ctx.set({**_ctx.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _ctx.reset(token)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            **_ctx.get(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _DevFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = _ctx.get()
        tag = " ".join(f"{k}={v}" for k, v in ctx.items() if k in ("run_id", "step_id"))
        extra = getattr(record, "fields", None)
        tail = f" {extra}" if extra else ""
        base = f"{record.levelname:<7} {record.name}: {record.getMessage()}{tail}"
        if tag:
            base = f"{base}  [{tag}]"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(json_logs: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if json_logs else _DevFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "google.auth", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
