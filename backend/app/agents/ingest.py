"""Stage 0 — Ingest one document: extract citable text (OCR where needed) and
profile it (type, filing party, date, summary). Results are cached by the
object's GCS generation so re-runs never re-OCR an unchanged file.

The source is streamed from Cloud Storage into a private scratch directory —
CRC32C-verified and pinned to the exact generation validated at upload — and
parsed from there, so even a 500 MB bundle is never held whole in memory.
"""

from __future__ import annotations

import errno
import shutil
import tempfile
from pathlib import Path
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud.storage.exceptions import DataCorruption

from app.agents.base import AgentContext, AgentResult
from app.agents.schemas import DocProfile, IngestOutput
from app.harness.resilience import PermanentStepError, RetryableStepError
from app.ingest.extract import Extracted, extract

PROFILE_SYSTEM = (
    "You classify documents filed in proceedings before the DIFC Courts (Dubai International Financial Centre). "
    "Given the file name and the opening text, identify the document type, a short label a judge would use "
    "(e.g. 'Particulars of Claim', 'Defence', 'Order 3', 'Contract', 'Delay expert report — Claimant'), "
    "which party filed it, the date on its face, and a neutral two-sentence summary. Use only the text provided."
)
OPENING_CHARS = 30_000


class IngestAgent:
    name = "ingest"

    async def run(self, ctx: AgentContext) -> AgentResult:
        doc_id = ctx.key
        assert doc_id, "ingest requires a document key"
        doc = await ctx.repo.get_document(ctx.case_id, doc_id)
        if not doc:
            raise PermanentStepError(f"document {doc_id} not found", "A document record is missing")

        cache_uri = f"gs://{ctx.settings.artifact_bucket}/cache/ingest/{ctx.case_id}/{doc_id}-{doc.get('generation')}.json"
        if await ctx.gcs.exists(cache_uri):
            cached = await ctx.gcs.read_json(cache_uri)
            await self._record(ctx, doc_id, cached)
            return AgentResult(output=cached)

        ex = await self._extract(ctx, doc)
        for r in ex.llm_results:
            ctx.track(r)
        if not ex.segments:
            raise PermanentStepError(
                f"no readable text in {doc_id}",
                f"{doc['name']} could not be read — re-upload a clearer copy",
            )

        prof = await ctx.llm.generate(
            schema=DocProfile, system=PROFILE_SYSTEM, tier="flash", temperature=0.0,
            contents=[f"File name: {doc['name']}\n\nOpening text:\n{_opening(ex)}"],
        )
        ctx.track(prof)
        p = prof.data
        out = IngestOutput(
            doc_id=doc_id, name=doc["name"], label=p.label.strip() or p.doc_type, doc_type=p.doc_type,
            filed_by=p.filed_by, doc_date=p.doc_date, summary=p.summary, pages=ex.pages,
            segments=ex.segments, unreadable=ex.unreadable, ocr_pages=ex.ocr_pages,
        ).model_dump()
        await ctx.gcs.write_json(cache_uri.removeprefix(f"gs://{ctx.settings.artifact_bucket}/"), out)
        await self._record(ctx, doc_id, out)
        return AgentResult(output=out)

    @staticmethod
    async def _extract(ctx: AgentContext, doc: dict[str, Any]) -> Extracted:
        """Stream the source to scratch, then parse it from disk."""
        s = ctx.settings
        if s.scratch_dir:
            Path(s.scratch_dir).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="vtx-ingest-", dir=s.scratch_dir or None))  # mode 0700, unique per step
        try:
            path = tmp / f"source.{doc['ext']}"
            try:
                await ctx.gcs.download_to_file(s.case_bucket, doc["object_name"], path, generation=doc.get("generation"))
            except NotFound as exc:
                raise PermanentStepError(
                    f"source object missing: {doc['object_name']}#{doc.get('generation')}",
                    f"{doc['name']} is no longer in storage — upload it again",
                ) from exc
            except DataCorruption as exc:  # CRC32C mismatch: corrupted in transit, a retry fetches it again
                raise RetryableStepError(f"checksum mismatch downloading {doc['object_name']}",
                                         "A document download was corrupted") from exc
            except OSError as exc:
                if exc.errno == errno.ENOSPC:  # scratch full: other ingests finishing will free it
                    raise RetryableStepError("scratch space exhausted", "The worker ran out of scratch space") from exc
                raise
            try:
                return await extract(path, doc["ext"], ctx.llm, s)
            except ValueError as exc:
                raise PermanentStepError(str(exc), f"{doc['name']} is not a supported document") from exc
        finally:
            # A parse thread orphaned by a step timeout may still hold the file open; on POSIX its
            # data stays readable until that handle closes, so removing the directory now is safe.
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    async def _record(ctx: AgentContext, doc_id: str, out: dict) -> None:
        await ctx.repo.update_document(ctx.case_id, doc_id, {
            "status": "unreadable" if out.get("unreadable") else "ingested",
            "doc_type": out["doc_type"], "label": out["label"], "filed_by": out["filed_by"],
            "pages": out["pages"], "unreadable": out.get("unreadable", [])[:50],
        })


def _opening(ex: Extracted) -> str:
    """The first ``OPENING_CHARS`` of the document, without joining every page of a large bundle."""
    parts: list[str] = []
    size = 0
    for seg in ex.segments:
        piece = f"[{seg.ref}] {seg.text}"
        parts.append(piece)
        size += len(piece) + 1
        if size > OPENING_CHARS:
            break
    return "\n".join(parts)[:OPENING_CHARS]
