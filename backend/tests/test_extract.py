"""Ingestion: path-based extraction, bounded OCR fan-out, memory and event-loop behaviour, and
the ingest agent's download handling."""

from __future__ import annotations

import asyncio
import errno
import gc
import io
import os
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("VTX_PROJECT_ID", "test-project")

from google.api_core.exceptions import NotFound  # noqa: E402
from google.cloud.storage.exceptions import DataCorruption  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from app.agents.ingest import IngestAgent, _opening  # noqa: E402
from app.agents.schemas import OcrPage, OcrResult, Segment  # noqa: E402
from app.config import Settings  # noqa: E402
from app.harness.resilience import PermanentStepError, RetryableStepError  # noqa: E402
from app.ingest.extract import Extracted, extract  # noqa: E402
from tests.pdfgen import make_pdf, text_page  # noqa: E402


def _settings(**kw) -> Settings:
    return Settings(project_id="test-project", **kw)


class FakeOcr:
    """Stands in for Gemini OCR: 'transcribes' each page of the sub-PDF it receives and records
    how many calls were in flight at once. Batches of ``fail_size`` pages raise."""

    def __init__(self, delay: float = 0.05, fail_size: int | None = None):
        self.delay, self.fail_size = delay, fail_size
        self.calls = self.inflight = self.max_inflight = 0

    async def generate(self, *, contents, **_kw):
        self.calls += 1
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.delay)
            n = len(PdfReader(io.BytesIO(contents[0].inline_data.data)).pages)  # a valid sub-PDF
            if n == self.fail_size:
                raise RuntimeError("model unavailable")
            pages = [OcrPage(page=i, text=f"transcribed {i}", readable=True) for i in range(1, n + 1)]
            return SimpleNamespace(data=OcrResult(pages=pages))
        finally:
            self.inflight -= 1


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- PDF
async def test_text_layer_kept_and_scanned_pages_ocrd_in_bounded_parallel_batches(tmp_path):
    path = _write(tmp_path, "b.pdf", make_pdf([text_page(1), None, None, text_page(4), None, None, None]))
    llm = FakeOcr()
    out = await extract(path, "pdf", llm, _settings(ocr_pages_per_call=2, ocr_max_inflight_batches=2))

    assert out.pages == 7 and out.ocr_pages == 5 and out.unreadable == []
    by_ref = {s.ref: s.text for s in out.segments}
    assert list(by_ref) == [f"p. {i}" for i in range(1, 8)]
    assert by_ref["p. 1"].startswith("Page 1 line 1:") and by_ref["p. 4"].startswith("Page 4 line 1:")
    # OCR batches [2,3] [5,6] [7]: each sub-PDF page maps back to its page in the bundle
    assert (by_ref["p. 2"], by_ref["p. 3"], by_ref["p. 7"]) == ("transcribed 1", "transcribed 2", "transcribed 1")
    assert llm.calls == 3 and llm.max_inflight == 2


async def test_failed_ocr_batch_marks_only_its_pages_unreadable(tmp_path):
    path = _write(tmp_path, "b.pdf", make_pdf([None] * 5))
    out = await extract(path, "pdf", FakeOcr(fail_size=1), _settings(ocr_pages_per_call=2))
    assert out.unreadable == ["p. 5"]
    assert [s.ref for s in out.segments] == ["p. 1", "p. 2", "p. 3", "p. 4"]


def _encrypted(user_password: str) -> bytes:
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(make_pdf([text_page(1)]))).pages:
        writer.add_page(page)
    writer.encrypt(user_password=user_password, owner_password="owner-secret", algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def test_password_protected_pdf_is_reported_not_raised(tmp_path):
    out = await extract(_write(tmp_path, "p.pdf", _encrypted("secret")), "pdf", None, _settings())
    assert (out.pages, out.segments, out.unreadable) == (0, [], ["whole document (password protected)"])


async def test_pdf_with_only_an_owner_password_is_read(tmp_path):
    out = await extract(_write(tmp_path, "o.pdf", _encrypted("")), "pdf", None, _settings())
    assert out.pages == 1 and out.segments[0].text.startswith("Page 1 line 1:")


async def test_corrupt_pdf_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        await extract(_write(tmp_path, "c.pdf", b"%PDF-1.4\nthis is not really a pdf"), "pdf", None, _settings())


async def test_scanned_bundle_memory_stays_bounded(tmp_path):
    """Page images must not accumulate on the heap (pypdf's object cache, PdfWriter garbage cycles)."""
    path = _write(tmp_path, "scan.pdf", make_pdf([None] * 300, image_bytes=128 * 1024))  # ~37.5 MiB
    size = path.stat().st_size
    gc.collect()
    tracemalloc.start()
    try:
        out = await extract(path, "pdf", FakeOcr(delay=0.002),
                            _settings(ocr_pages_per_call=5, ocr_max_inflight_batches=2))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out.ocr_pages == 300
    assert peak < 0.25 * size, f"peak heap {peak / 2**20:.1f} MiB for a {size / 2**20:.1f} MiB file"


async def test_parsing_does_not_block_the_event_loop(tmp_path):
    path = _write(tmp_path, "big.pdf", make_pdf([text_page(i) for i in range(1, 301)]))
    gaps: list[float] = []
    stop = asyncio.Event()

    async def ticker() -> None:
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            gaps.append(now - last - 0.005)
            last = now

    tick = asyncio.create_task(ticker())
    await asyncio.sleep(0.02)  # ticker is mid-sleep when parsing starts, so a blocked loop shows up as one long gap
    out = await extract(path, "pdf", None, _settings())
    stop.set()
    await tick
    assert len(out.segments) == 300
    assert gaps and max(gaps) < 0.15, f"event loop stalled {max(gaps, default=0) * 1000:.0f} ms"  # ~750 ms on the loop


# ---------------------------------------------------------------- other formats
async def test_txt_is_read_in_page_sized_pieces_without_bom(tmp_path):
    path = _write(tmp_path, "t.txt", b"\xef\xbb\xbf" + ("A" * 3000 + "B" * 3000 + "C" * 10).encode())
    out = await extract(path, "txt", None, _settings())
    assert out.pages == 3
    assert [s.text for s in out.segments] == ["A" * 3000, "B" * 3000, "C" * 10]


# ---------------------------------------------------------------- ingest agent
def _ctx(tmp_path: Path, download) -> SimpleNamespace:
    s = _settings(scratch_dir=str(tmp_path / "scratch"))
    return SimpleNamespace(settings=s, gcs=SimpleNamespace(download_to_file=download), llm=None)


DOC = {"ext": "txt", "object_name": "cases/c1/d1/x.txt", "generation": 42, "name": "claim.txt"}


async def test_ingest_streams_pinned_generation_to_scratch_and_cleans_up(tmp_path):
    seen: dict = {}

    async def download(bucket, object_name, path, generation=None):
        seen.update(object_name=object_name, path=path, generation=generation)
        path.write_text("Claim form. " * 600)
        return path.stat().st_size

    ex = await IngestAgent._extract(_ctx(tmp_path, download), DOC)
    assert ex.pages == 3 and ex.segments[0].text.startswith("Claim form.")
    assert seen["generation"] == 42 and seen["object_name"] == DOC["object_name"]
    assert seen["path"].parent.parent == tmp_path / "scratch"
    assert list((tmp_path / "scratch").iterdir()) == []  # scratch removed once parsed


@pytest.mark.parametrize(("exc", "expected"), [
    (NotFound("gone"), PermanentStepError),
    (DataCorruption(None, "crc32c mismatch"), RetryableStepError),
    (OSError(errno.ENOSPC, "No space left on device"), RetryableStepError),
])
async def test_ingest_download_failures_are_classified(tmp_path, exc, expected):
    async def download(*_a, **_kw):
        raise exc

    with pytest.raises(expected):
        await IngestAgent._extract(_ctx(tmp_path, download), DOC)
    assert list((tmp_path / "scratch").iterdir()) == []


async def test_ingest_unparseable_source_fails_permanently(tmp_path):
    async def download(bucket, object_name, path, generation=None):
        path.write_bytes(b"%PDF-1.4\nnot really")

    with pytest.raises(PermanentStepError):
        await IngestAgent._extract(_ctx(tmp_path, download), {**DOC, "ext": "pdf", "name": "c.pdf"})


def test_opening_is_the_prefix_of_the_full_text():
    segs = [Segment(ref=f"p. {i}", text="x" * (i * 97 % 4000)) for i in range(1, 200)]
    assert _opening(Extracted(pages=199, segments=segs)) == "\n".join(f"[{s.ref}] {s.text}" for s in segs)[:30_000]
    assert _opening(Extracted(pages=1, segments=[Segment(ref="p. 1", text="hi")])) == "[p. 1] hi"
