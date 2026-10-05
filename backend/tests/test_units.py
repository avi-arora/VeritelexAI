"""Unit tests for resilience primitives, file sniffing, citations and API formatting."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("VTX_PROJECT_ID", "test-project")

from app.agents.corpus import citation_index, labelled, resolve  # noqa: E402
from app.harness.resilience import (  # noqa: E402
    CircuitBreaker, PermanentStepError, RetryableStepError, SchemaError, backoff_delay, is_retryable, retry_async,
)
from app.ingest.filetypes import MIN_OOXML_BYTES, kind_for_name, matches, ooxml_kind, sniff  # noqa: E402


# ---------------------------------------------------------------- resilience
def test_retryable_classification():
    assert is_retryable(RetryableStepError("x"))
    assert is_retryable(SchemaError("x"))
    assert not is_retryable(PermanentStepError("x"))
    assert is_retryable(TimeoutError())
    assert not is_retryable(ValueError())


def test_transport_errors_from_storage_and_auth_are_retryable():
    import requests
    from google.auth.exceptions import TransportError

    assert is_retryable(requests.exceptions.ConnectionError("reset"))
    assert is_retryable(requests.exceptions.ConnectTimeout("slow"))  # subclass, matched via the MRO
    assert is_retryable(requests.exceptions.ChunkedEncodingError("cut"))
    assert is_retryable(TransportError("metadata server unavailable"))
    assert not is_retryable(requests.exceptions.InvalidURL("bad"))  # a bug, not a blip


def test_backoff_is_bounded():
    for attempt in range(1, 20):
        assert 0 <= backoff_delay(attempt, base=1, cap=10) <= 10


async def test_retry_async_recovers_then_gives_up_on_permanent():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableStepError("transient")
        return "ok"

    assert await retry_async(flaky, attempts=3, base=0.001, cap=0.001) == "ok"

    async def permanent():
        raise PermanentStepError("nope")

    with pytest.raises(PermanentStepError):
        await retry_async(permanent, attempts=5, base=0.001)


def test_circuit_breaker_opens_and_half_opens():
    br = CircuitBreaker("m", threshold=2, cooldown=0.0)
    br.failure()
    assert br.allow()
    br.failure()
    assert br.state == "half-open"  # cooldown 0 -> immediately probe-able
    br.success()
    assert br.state == "closed"
    br2 = CircuitBreaker("m2", threshold=1, cooldown=60)
    br2.failure()
    assert not br2.allow()


# ---------------------------------------------------------------- filetypes
def _ooxml(part: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr(part, "<x/>")
    return buf.getvalue()


def test_sniff_and_match():
    assert sniff(b"%PDF-1.7\n") == "pdf"
    assert matches("pdf", b"%PDF-1.4")
    assert not matches("pdf", b"\x89PNG\r\n\x1a\n")
    assert not matches("png", b"%PDF-1.4")
    assert matches("txt", "Hello ¶ world".encode())
    assert not matches("txt", b"\x00\x01binary")
    assert kind_for_name("../../evil.PDF").ext == "pdf"
    assert kind_for_name("macro.docm") is None


def test_ooxml_kind_and_traversal_rejected():
    assert ooxml_kind(_ooxml("word/document.xml")) == "docx"
    assert ooxml_kind(_ooxml("xl/workbook.xml")) == "xlsx"
    assert ooxml_kind(_ooxml("../evil.xml")) is None
    assert ooxml_kind(b"not a zip") is None


def test_ooxml_kind_reads_file_objects_and_survives_malformed_zips(tmp_path):
    docx = _ooxml("word/document.xml")
    assert ooxml_kind(io.BytesIO(docx)) == "docx"  # seekable reader, as used for ranged GCS reads
    (tmp_path / "a.docx").write_bytes(docx)
    assert ooxml_kind(tmp_path / "a.docx") == "docx"
    assert len(docx) >= MIN_OOXML_BYTES
    assert ooxml_kind(b"PK\x03\x04") is None  # truncated container
    # An entry flagged as UTF-8 whose name is not valid UTF-8 raised UnicodeDecodeError (a 500).
    bad = _ooxml("word/d\u00e9.xml").replace("d\u00e9".encode(), b"d\xff\xfe")
    assert ooxml_kind(bad) is None


# ---------------------------------------------------------------- citations
def test_citation_resolution():
    docs = labelled({
        "d1": {"label": "Particulars of Claim", "segments": [{"ref": "¶ 12", "text": "The works were delayed."}]},
        "d2": {"label": "Order", "segments": [{"ref": "p. 2", "text": "Permission granted."}]},
        "d3": {"label": "Order", "segments": [{"ref": "p. 1", "text": "Second order."}]},
    }, ["d1", "d2", "d3"])
    assert [d["cite_label"] for d in docs] == ["Particulars of Claim", "Order", "Order (2)"]
    idx = citation_index(docs)
    assert resolve("Particulars of Claim, ¶12", idx) == "The works were delayed."
    assert resolve("Order (2), p. 1", idx) == "Second order."
    assert resolve("Particulars of Claim, ¶ 99", idx) is None
    assert resolve("Witness statement, p. 1", idx) is None


# ---------------------------------------------------------------- API formatting
def test_relative_time_and_summary():
    from app.api.routes import relative, to_summary

    t = datetime.now(UTC)
    assert relative(t) == "Just now"
    assert relative(t - timedelta(minutes=4)) == "4 min ago"
    assert relative(t - timedelta(hours=1, minutes=5)) == "1 hour ago"
    assert relative(t - timedelta(days=1, hours=2)) == "Yesterday"
    assert relative(t - timedelta(days=13)) == "13 days ago"
    s = to_summary({"id": "c0123456789ab", "doc_count": 1, "page_count": 1842, "status": "ready",
                    "updated_at": t, "created_at": t})
    assert s["docs"] == "1 document" and s["pages"] == "1,842 pages" and s["isNew"]
    assert s["no"] == "Pending"
