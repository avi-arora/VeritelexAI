"""Public REST API (``/api/v1``) consumed by the Next.js app.

Security notes:
* TODO(security): there is no end-user authentication — by POC decision the
  login screen is static. In production the API service is private
  (Cloud Run IAM, no unauthenticated access) and reachable only from the web
  service's identity; add real user auth before any wider exposure.
* All path ids are validated against strict patterns; all bodies are Pydantic
  models with length limits; Firestore is accessed only through the SDK
  (no query strings are built from user input).
* Uploads go straight to GCS with short-lived V4 signed URLs restricted to one
  object, one Content-Type and a size range. The object is then re-validated
  server-side (size, magic bytes, OOXML structure) before any agent reads it.
  TODO(security): no malware scanning / content disarm is performed.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.container import Container
from app.domain.models import (
    AskAnswerOut,
    AskRequest,
    AskReviewOut,
    AskScope,
    AskSummary,
    AskView,
    CaseDetail,
    CaseField,
    CaseSummary,
    CouncilMemberOut,
    CouncilModelsOut,
    CouncilRunMember,
    CreateCaseRequest,
    DocumentOut,
    RunCounts,
    RunSummary,
    RunView,
    StartRunRequest,
    SteelmanOut,
    StepView,
    SynthesisOut,
    UpdateCaseRequest,
    UploadRequest,
    UploadResponse,
    UploadTarget,
)
from app.harness.resilience import PermanentStepError
from app.ingest.filetypes import KINDS, MIN_OOXML_BYTES, kind_for_name, matches, ooxml_kind
from app.logging_setup import get_logger
from app.storage.firestore import now

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

CaseId = Annotated[str, Path(pattern=r"^c[0-9a-f]{12}$")]
DocId = Annotated[str, Path(pattern=r"^d[0-9a-f]{12}$")]
RunId = Annotated[str, Path(pattern=r"^r[0-9a-f]{12}$")]
AskId = Annotated[str, Path(pattern=r"^q[0-9a-f]{12}$")]
SECTIONS = ("background", "matrix", "mapping", "issues", "tools", "council", "questions")
ACTIVE = ("queued", "ingesting", "ai")
UNAVAILABLE = "Not enabled in Model Garden for this project"
EDITABLE_FIELDS = {"Claim number", "Division", "Case title", "Claimant", "Defendant", "Case type", "Amount claimed"}
DOC_STATUS = {
    "pending_upload": ("Uploading", "grey"), "uploaded": ("Queued", "grey"), "ingested": ("Read", "green"),
    "unreadable": ("Partly unreadable", "amber"), "rejected": ("Rejected", "red"), "failed": ("Could not be read", "red"),
    "abandoned": ("Upload cancelled", "grey"),
}
# Background tasks must be referenced or the event loop may garbage-collect them.
_background: set[asyncio.Task] = set()


def container(request: Request) -> Container:
    return request.app.state.container


C = Annotated[Container, Depends(container)]


# ============================================================== formatting
def _iso(ts: Any) -> str:
    return ts.astimezone(UTC).isoformat() if isinstance(ts, datetime) else ""


def relative(ts: Any) -> str:
    if not isinstance(ts, datetime):
        return ""
    secs = (datetime.now(UTC) - ts).total_seconds()
    if secs < 90:
        return "Just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h > 1 else ''} ago"
    days = int(secs // 86400)
    if days == 1:
        return "Yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return ts.strftime("%b %Y")


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def to_summary(c: dict[str, Any]) -> dict[str, Any]:
    docs, pages = int(c.get("doc_count") or 0), int(c.get("page_count") or 0)
    return {
        "id": c["id"], "no": c.get("no") or "Pending", "title": c.get("title") or "New case",
        "type": c.get("type") or "Being identified", "division": c.get("division") or "—",
        "docs": _plural(docs, "document"), "pages": _plural(pages, "page") if pages else "—",
        "status": c.get("status") or "queued", "pct": c.get("pct"), "at": c.get("at"),
        "note": c.get("note") or "", "updated": relative(c.get("updated_at")), "updatedAt": _iso(c.get("updated_at")),
        "past": bool(c.get("past")),
        "isNew": isinstance(c.get("created_at"), datetime) and datetime.now(UTC) - c["created_at"] < timedelta(hours=24),
    }


def to_detail(c: dict[str, Any]) -> CaseDetail:
    return CaseDetail(
        **to_summary(c), subtitle=c.get("subtitle") or "",
        reportReadyAt=_iso(c.get("report_ready_at")) or None,
        fields=[CaseField(**f) for f in c.get("fields") or []], latestRunId=c.get("latest_run_id"),
    )


def to_doc(d: dict[str, Any]) -> DocumentOut:
    s, tone = DOC_STATUS.get(d.get("status", ""), ("Unknown", "grey"))
    pages = d.get("pages")
    return DocumentOut(
        id=d["id"], n=d.get("name", ""), t=d.get("label") or d.get("doc_type") or "Identifying…",
        p=f"{pages} pp" if pages else "—", ext=d.get("kind", "FILE"), by=d.get("filed_by") or "—",
        s=s, tone=tone, status=d.get("status", ""), sizeBytes=d.get("size"),
    )


async def _case_or_404(c: Container, case_id: str) -> dict[str, Any]:
    case = await c.repo.get_case(case_id)
    if not case:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


def _track(t: asyncio.Task) -> asyncio.Task:
    _background.add(t)
    t.add_done_callback(_task_done)
    return t


def _task_done(t: asyncio.Task) -> None:
    _background.discard(t)
    if not t.cancelled() and t.exception() is not None:
        log.warning("background task failed: %s", t.exception())


def _spawn(coro: Any) -> None:
    _track(asyncio.create_task(coro))


# Last self-healing attempt per run/ask in this process: reads are polled every few seconds, and
# one reconcile a minute is plenty (it is idempotent, but each one is a Firestore transaction).
_healed: dict[str, float] = {}


def _throttle(key: str, every_s: float = 60.0) -> bool:
    t = time.monotonic()
    if t - _healed.get(key, float("-inf")) < every_s:
        return False
    if len(_healed) > 5000:
        _healed.clear()
    _healed[key] = t
    return True


async def _maybe_reconcile(c: Container, case: dict[str, Any]) -> None:
    """Self-healing on read.

    * A run with no activity for ``stale_run_seconds`` is reconciled.
    * Uploads that ended without starting a run are picked up. If the tab closed mid-batch, the
      last pending upload simply expires and no completion is left to start the analysis; once
      the case has been idle past the link lifetime, the run starts with the files that made it.
    """
    run_id = case.get("latest_run_id")
    ts = case.get("updated_at")
    idle = (now() - ts).total_seconds() if isinstance(ts, datetime) else 0.0
    if not run_id:
        if (not case.get("draft") and case.get("status") == "queued" and idle > c.settings.upload_url_ttl_s + 60
                and _throttle(f"start:{case['id']}")):
            _spawn(_start_when_settled(c, case["id"]))
        return
    if case.get("status") in ACTIVE and idle > c.settings.stale_run_seconds and _throttle(f"run:{run_id}"):
        _spawn(c.orchestrator.reconcile(case["id"], run_id))


def _maybe_reconcile_ask(c: Container, case_id: str, ask: dict[str, Any]) -> None:
    """Same self-healing for a question whose run has gone quiet (e.g. after a worker restart)."""
    ts = ask.get("updated_at")
    if (ask.get("status") == "running" and isinstance(ts, datetime)
            and (now() - ts).total_seconds() > c.settings.stale_run_seconds and _throttle(f"ask:{ask['id']}")):
        _spawn(c.orchestrator.reconcile(case_id, ask["id"]))


async def _start_when_settled(c: Container, case_id: str) -> None:
    try:
        await _maybe_start(c, case_id, await c.repo.list_documents(case_id))
    except Exception:  # best effort: the next read of the case tries again
        log.exception("could not start the analysis for case %s", case_id)


# ============================================================== cases
@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(c: C) -> list[dict[str, Any]]:
    cases = [x for x in await c.repo.list_cases() if not x.get("draft")]
    for x in cases:
        await _maybe_reconcile(c, x)
    return [to_summary(x) for x in cases]


@router.post("/cases", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def create_case(body: CreateCaseRequest, c: C) -> CaseDetail:
    case_id = "c" + uuid.uuid4().hex[:12]
    data = {
        "title": (body.title or "").strip() or None, "status": "queued", "pct": 0, "at": None,
        "note": "Waiting for documents", "draft": True, "doc_count": 0, "confirmed": False,
    }
    await c.repo.create_case(case_id, data)
    return to_detail(await _case_or_404(c, case_id))


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case(case_id: CaseId, c: C) -> CaseDetail:
    case = await _case_or_404(c, case_id)
    await _maybe_reconcile(c, case)
    return to_detail(case)


@router.patch("/cases/{case_id}", response_model=CaseDetail)
async def update_case(case_id: CaseId, body: UpdateCaseRequest, c: C) -> CaseDetail:
    case = await _case_or_404(c, case_id)
    upd: dict[str, Any] = {}
    if body.fields is not None:
        current = {f["k"]: f for f in case.get("fields") or []}
        for f in body.fields:
            if f.k not in EDITABLE_FIELDS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Field '{f.k}' cannot be edited")
            if len(f.v) > 500:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Field value too long")
            prev = current.get(f.k, {})
            changed = prev.get("v") != f.v
            current[f.k] = {"k": f.k, "v": f.v.strip(), "src": "Edited by you" if changed else prev.get("src", ""),
                            "full": prev.get("full", f.k == "Case title")}
        fields = list(current.values())
        by_k = {f["k"]: f["v"] for f in fields}
        upd |= {"fields": fields, "no": by_k.get("Claim number") or case.get("no"),
                "title": by_k.get("Case title") or case.get("title"), "type": by_k.get("Case type") or case.get("type"),
                "division": by_k.get("Division") or case.get("division"),
                "claimant": by_k.get("Claimant"), "defendant": by_k.get("Defendant")}
    if body.confirmed is not None:
        upd["confirmed"] = body.confirmed
    if upd:
        await c.repo.update_case(case_id, upd)
    return to_detail(await _case_or_404(c, case_id))


# ============================================================== documents
@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
async def list_documents(case_id: CaseId, c: C) -> list[DocumentOut]:
    await _case_or_404(c, case_id)
    return [to_doc(d) for d in await c.repo.list_documents(case_id) if d.get("status") != "abandoned"]


@router.post("/cases/{case_id}/uploads", response_model=UploadResponse)
async def create_uploads(case_id: CaseId, body: UploadRequest, c: C) -> UploadResponse:
    s = c.settings
    await _case_or_404(c, case_id)
    if len(body.files) > s.max_files_per_upload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {s.max_files_per_upload} files per upload")
    planned = []
    for f in body.files:
        kind = kind_for_name(f.name)
        if not kind:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                f"{f.name}: unsupported file type (allowed: {', '.join(sorted({k.ext for k in KINDS.values()}))})")
        if f.size > s.max_upload_bytes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{f.name}: file is larger than {s.max_upload_bytes // 2**20} MB")
        doc_id = "d" + uuid.uuid4().hex[:12]
        # Random object name: the user-supplied file name never becomes a storage path.
        planned.append((f, kind, doc_id, f"cases/{case_id}/{doc_id}/{uuid.uuid4().hex}.{kind.ext}"))
    # Each link is an IAM signBlob round trip, so sign them concurrently (bounded by the GCS
    # helper's I/O pool). Signing has no side effects; the records are then created in one atomic
    # batch, so a failure part-way never leaves orphan "pending" records that would hold back the
    # automatic start of the analysis.
    signed = await asyncio.gather(*(c.gcs.signed_put_url(obj, kind.mime, s.max_upload_bytes) for _, kind, _, obj in planned))
    await c.repo.create_documents(case_id, {
        doc_id: {
            "name": f.name.replace("/", "_").replace("\\", "_")[:255], "ext": kind.ext, "kind": kind.label,
            "content_type": kind.mime, "declared_size": f.size, "object_name": obj, "status": "pending_upload",
        }
        for f, kind, doc_id, obj in planned
    })
    return UploadResponse(caseId=case_id, targets=[
        UploadTarget(documentId=doc_id, name=f.name, uploadUrl=url, headers=headers)
        for (f, _, doc_id, _), (url, headers) in zip(planned, signed, strict=True)
    ])


@router.post("/cases/{case_id}/documents/{doc_id}/complete", response_model=DocumentOut)
async def complete_upload(case_id: CaseId, doc_id: DocId, c: C) -> DocumentOut:
    s = c.settings
    case = await _case_or_404(c, case_id)
    doc = await c.repo.get_document(case_id, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if doc["status"] == "abandoned":
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload was cancelled; add the file again")
    if doc["status"] != "pending_upload":
        return to_doc(doc)  # idempotent

    meta = await c.gcs.stat(s.case_bucket, doc["object_name"])
    if meta is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The file has not been uploaded yet")
    reason = None
    if not meta["size"] or meta["size"] > s.max_upload_bytes:
        reason = "file size is outside the allowed range"
    else:
        head = await c.gcs.read_head(s.case_bucket, doc["object_name"])
        if not matches(doc["ext"], head):
            reason = "file content does not match its extension"
        elif doc["ext"] in ("docx", "xlsx") and meta["size"] > 100 * 2**20:
            reason = "Office documents larger than 100 MB are not supported"
        elif doc["ext"] in ("docx", "xlsx") and meta["size"] < MIN_OOXML_BYTES:
            reason = "file is not a valid Office document"
        elif doc["ext"] in ("docx", "xlsx"):
            # Ranged reads of the zip central directory only — the file is never downloaded here.
            kind = await c.gcs.inspect(s.case_bucket, doc["object_name"], ooxml_kind, generation=meta["generation"])
            if kind != doc["ext"]:
                reason = "file is not a valid Office document"
    if reason:
        # Only a still-pending upload is rejected; a concurrent complete/abandon that already moved it on wins.
        if await c.repo.transition_document(case_id, doc_id, "pending_upload", {"status": "rejected", "reject_reason": reason}):
            await c.gcs.delete(s.case_bucket, doc["object_name"])
        log.warning("rejected upload %s/%s: %s", case_id, doc_id, reason)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{doc['name']}: {reason}")

    updated = await c.repo.transition_document(case_id, doc_id, "pending_upload", {
        "status": "uploaded", "size": meta["size"], "generation": meta["generation"], "crc32c": meta["crc32c"],
        "uploaded_at": now(),
    })
    if updated is None:  # lost a race: completed by a retry (fine) or abandoned meanwhile
        current = await c.repo.get_document(case_id, doc_id)
        if current and current.get("status") not in ("abandoned", "pending_upload"):
            return to_doc(current)
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload was cancelled; add the file again")
    docs = await c.repo.list_documents(case_id)
    uploaded = [d for d in docs if d.get("status") in ("uploaded", "ingested", "unreadable")]
    await c.repo.update_case(case_id, {"doc_count": len(uploaded), "draft": False})
    if case.get("draft"):
        await c.repo.update_case(case_id, {"note": "Uploading documents"})
    await _maybe_start(c, case_id, docs)
    return to_doc(updated)


@router.post("/cases/{case_id}/documents/{doc_id}/abandon", response_model=DocumentOut)
async def abandon_upload(case_id: CaseId, doc_id: DocId, c: C) -> DocumentOut:
    """The browser gave up on this file (its upload failed and the user skipped or removed it).

    Pending uploads hold back the automatic start of the analysis, so the record is closed
    explicitly, any bytes that did land are deleted, and the analysis starts if this was the
    last upload of the batch still outstanding. Idempotent.
    """
    s = c.settings
    await _case_or_404(c, case_id)
    doc = await c.repo.transition_document(case_id, doc_id, "pending_upload", {"status": "abandoned"})
    if doc is None:
        current = await c.repo.get_document(case_id, doc_id)
        if not current:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        if current.get("status") in ("abandoned", "rejected"):
            return to_doc(current)
        raise HTTPException(status.HTTP_409_CONFLICT, "This file has already been uploaded")
    await c.gcs.delete(s.case_bucket, doc["object_name"])
    await _maybe_start(c, case_id, await c.repo.list_documents(case_id))
    return to_doc(doc)


async def _maybe_start(c: Container, case_id: str, docs: list[dict[str, Any]]) -> None:
    """Start the analysis once no upload in the batch is still in flight.

    Abandoned uploads (signed URL expired, never completed) do not block the run.
    The idempotency key is derived from the exact document set, so concurrent
    completions and client retries collapse into a single run.
    """
    cutoff = now() - timedelta(seconds=c.settings.upload_url_ttl_s + 60)
    pending = [d for d in docs if d.get("status") == "pending_upload" and d.get("created_at") and d["created_at"] > cutoff]
    if pending:
        return
    ready = sorted(f"{d['id']}:{d.get('generation')}" for d in docs if d.get("status") in ("uploaded", "ingested", "unreadable"))
    if not ready or not any(d.get("status") == "uploaded" for d in docs):
        return
    key = "auto:" + hashlib.sha256("|".join(ready).encode()).hexdigest()[:24]
    await c.orchestrator.start_run(case_id, trigger="upload", idem_key=key)


# ============================================================== council
@router.get("/council/models", response_model=CouncilModelsOut)
async def council_models(c: C, refresh: Annotated[bool, Query()] = False) -> CouncilModelsOut:
    """The council's members and whether each one can answer right now.

    Availability is probed with a tiny request and cached (``council_status_ttl_s``). Probes run as
    background tasks with a bounded wait, so a slow model never blocks the page: a member still
    being checked reports ``unknown`` and the next poll picks up the result.
    """
    council = c.council
    ids = council.ids() if council is not None else []
    todo = ids if refresh else [i for i in ids if council.status(i)["status"] == "unknown"]
    if todo:
        tasks = [_track(asyncio.create_task(council.probe(i, force=refresh))) for i in todo]
        await asyncio.wait(tasks, timeout=25 if refresh else 8)
    members = []
    for i in ids:
        m, st = council.member(i), council.status(i)
        members.append(CouncilMemberOut(
            id=m.id, name=m.name, vendor=m.vendor, host=m.host, m=m.mono, c=m.color, models=list(m.models),
            status=st["status"], activeModel=st.get("activeModel"), detail=st.get("detail") or "",
            consoleUrl=council.console_url(m), checkedAt=_iso(st.get("checkedAt")) or None,
        ))
    return CouncilModelsOut(chair=council.chair_order() if ids else [], members=members)


def _step_state(st: dict[str, Any] | None) -> str:
    """Step status for the UI: a succeeded step whose agent reported ``unavailable``/``skipped`` shows that."""
    if not st:
        return "pending"
    if st.get("status") == "succeeded" and st.get("outcome") in ("unavailable", "skipped"):
        return st["outcome"]
    return st.get("status") or "pending"


def _step_error(st: dict[str, Any] | None, out: dict[str, Any] | None, state: str) -> str | None:
    if state == "unavailable":
        return (out or {}).get("detail") or UNAVAILABLE
    if state in ("failed", "retrying"):
        return (st or {}).get("user_error") or "This step could not complete"
    return None


def _council_states(members: list[str], steps: list[dict[str, Any]]) -> list[CouncilRunMember]:
    """Council progress of a version that has no finished summary yet (running, or failed before finalize)."""
    by_key = {s.get("key"): s for s in steps if s.get("spec") == "council"}
    out = []
    for mid in members:
        st = by_key.get(mid)
        state = _step_state(st)
        out.append(CouncilRunMember(
            id=mid, status=state, model=((st or {}).get("models") or [None])[0], error=_step_error(st, None, state),
        ))
    return out


# ============================================================== runs (report versions)
async def _versions(c: Container, case_id: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Runs oldest first, and run id -> 1-based version number (stable: runs are never deleted)."""
    runs = await c.repo.list_runs(case_id)
    return runs, {r["id"]: i for i, r in enumerate(runs, start=1)}


@router.get("/cases/{case_id}/runs", response_model=list[RunSummary])
async def list_versions(case_id: CaseId, c: C) -> list[RunSummary]:
    """Every report version of the case, newest first. Reports are stored per version and never overwritten."""
    case = await _case_or_404(c, case_id)
    await _maybe_reconcile(c, case)
    (runs, versions), legacy = await asyncio.gather(_versions(c, case_id), c.repo.legacy_report_run(case_id))
    published = case.get("report_run_id") or legacy

    async def summary(r: dict[str, Any]) -> RunSummary:
        council = [CouncilRunMember(**m) for m in r.get("council") or []]
        if not council and r.get("council_models"):
            council = _council_states(r["council_models"], await c.repo.list_steps_of(case_id, r["id"], "council"))
        counts = r.get("counts")
        source = r.get("source_run_id")
        return RunSummary(
            id=r["id"], version=versions[r["id"]], status=r.get("status") or "running", mode=r.get("mode") or "full",
            trigger=r.get("trigger") or "upload", sourceRunId=source, sourceVersion=versions.get(source) if source else None,
            createdAt=_iso(r.get("created_at")), finishedAt=_iso(r.get("finished_at")) or None,
            stage=r.get("stage") or "", pct=int(r.get("pct") or 0),
            # Versions from before versioning kept only the last report (the "legacy" one).
            hasReport=bool(r.get("report_ready_at")) or r["id"] in (published, legacy),
            published=r["id"] == published, docCount=int(r.get("doc_count") or len(r.get("doc_ids") or [])),
            counts=RunCounts(**counts) if counts else None, council=council,
        )

    return list(reversed(await asyncio.gather(*(summary(r) for r in runs))))


@router.post("/cases/{case_id}/runs", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
async def start_run(case_id: CaseId, c: C, body: StartRunRequest | None = None) -> RunView:
    """Start a new report version.

    ``mode="full"`` re-analyses the case's documents. ``mode="council"`` re-runs only the model
    council and the report assembly on a finished version's analysis (default: the published one).
    Earlier versions are kept, and the published report stays readable until the new one is ready.
    """
    case = await _case_or_404(c, case_id)
    req = body or StartRunRequest()
    latest = case.get("latest_run_id")
    if latest:
        run = await c.repo.get_run(case_id, latest)
        if run and run.get("status") == "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "An analysis is already running for this case")
    if req.mode == "council" and not c.orchestrator.council_ids():
        raise HTTPException(status.HTTP_409_CONFLICT, "The model council is not configured")
    # The same request within 30 s (double click, client retry) collapses into one version.
    window = int(now().timestamp() // 30)
    key = "manual:" + hashlib.sha256(f"{latest}|{req.mode}|{req.sourceRunId}|{window}".encode()).hexdigest()[:24]
    try:
        run_id = await c.orchestrator.start_run(
            case_id, trigger="manual", idem_key=key, mode=req.mode,
            source_run_id=req.sourceRunId if req.mode == "council" else None,
        )
    except PermanentStepError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.user_message) from exc
    return await _run_view(c, case_id, run_id)


@router.get("/cases/{case_id}/runs/latest", response_model=RunView)
async def latest_run(case_id: CaseId, c: C) -> RunView:
    case = await _case_or_404(c, case_id)
    if not case.get("latest_run_id"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis has run for this case")
    await _maybe_reconcile(c, case)
    return await _run_view(c, case_id, case["latest_run_id"])


@router.get("/cases/{case_id}/runs/{run_id}", response_model=RunView)
async def get_run(case_id: CaseId, run_id: RunId, c: C) -> RunView:
    await _case_or_404(c, case_id)
    return await _run_view(c, case_id, run_id)


@router.post("/cases/{case_id}/runs/{run_id}/resume", response_model=RunView)
async def resume_run(case_id: CaseId, run_id: RunId, c: C) -> RunView:
    """Resume from checkpoints: re-dispatch stranded steps of a running run, or
    reset the failed/skipped steps of a failed/partial run (succeeded steps are reused)."""
    case = await _case_or_404(c, case_id)
    run = await c.repo.get_run(case_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run["status"] == "running":
        await c.orchestrator.reconcile(case_id, run_id, force=True)
    elif run["status"] in ("failed", "partial"):
        # Resuming makes a run the latest and lets it publish, so an older version must never be
        # resumed over a newer one: start a new run instead.
        if run_id != case.get("latest_run_id"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Only the most recent version can be resumed. Start a new run instead.")
        await c.orchestrator.retry_failed(case_id, run_id)
    return await _run_view(c, case_id, run_id)


async def _run_view(c: Container, case_id: str, run_id: str) -> RunView:
    run = await c.repo.get_run(case_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    order = {sp.name: i for i, sp in enumerate(c.orchestrator.dag.specs)}
    steps = sorted(await c.repo.list_steps(case_id, run_id), key=lambda s: (order.get(s["spec"], 99), s["id"]))
    return RunView(
        id=run_id, status=run.get("status", ""), stage=run.get("stage", ""), pct=int(run.get("pct") or 0),
        createdAt=_iso(run.get("created_at")), updatedAt=_iso(run.get("updated_at")),
        mode=run.get("mode") or "full", sourceRunId=run.get("source_run_id"),
        steps=[StepView(
            id=s["id"], agent=s["agent"], status=s["status"], attempts=int(s.get("attempts", 0)),
            error=s.get("user_error") or (UNAVAILABLE if s.get("outcome") == "unavailable" else None),
            startedAt=_iso(s.get("started_at")) or None, finishedAt=_iso(s.get("finished_at")) or None,
            outcome=s.get("outcome"), reused=bool(s.get("reused_from")),
        ) for s in steps],
    )


# ============================================================== report
@router.get("/cases/{case_id}/report/{section}")
async def get_report(
    case_id: CaseId, section: Annotated[str, Path(pattern=r"^[a-z]{3,12}$")], c: C,
    run: Annotated[str | None, Query(pattern=r"^r[0-9a-f]{12}$")] = None,
) -> dict[str, Any]:
    """One section of report version ``run`` (default: the published version)."""
    if section not in SECTIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown report section")
    case = await _case_or_404(c, case_id)
    rep = await c.repo.get_report(case_id, section, run or case.get("report_run_id"))
    if not rep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This section is not available for this version"
                            if run else "This section has not been generated yet")
    return {"runId": rep.get("run_id"), "updatedAt": _iso(rep.get("updated_at")), "data": rep.get("data")}


# ============================================================== ask the council
# Step outputs are immutable until the step runs again (which changes finished_at), so they are
# cached per (uri, finished_at): a question page is polled every few seconds.
_outputs_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_OUTPUTS_CACHE_MAX = 300


async def _outputs(c: Container, steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Outputs of the succeeded steps, keyed by step id."""
    done = [s for s in steps if s.get("status") == "succeeded" and s.get("output_uri")]

    async def one(s: dict[str, Any]) -> dict[str, Any]:
        key = (s["output_uri"], _iso(s.get("finished_at")))
        if key in _outputs_cache:
            _outputs_cache.move_to_end(key)
            return _outputs_cache[key]
        data = await c.gcs.read_json(s["output_uri"])
        _outputs_cache[key] = data
        while len(_outputs_cache) > _OUTPUTS_CACHE_MAX:
            _outputs_cache.popitem(last=False)
        return data

    try:
        datas = await asyncio.gather(*(one(s) for s in done))
    except Exception as exc:  # noqa: BLE001 - the page polls again
        log.warning("could not read step outputs: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The answers could not be read just now; retrying") from exc
    return {s["id"]: d for s, d in zip(done, datas, strict=True)}


def _ask_status(ask: dict[str, Any], answered: list[str] | None) -> str:
    s = ask.get("status") or "running"
    if s in ("succeeded", "partial") and answered is not None and not answered:
        return "failed"  # every member was unavailable or failed: there is no answer to show
    return s


def _ask_summary(ask: dict[str, Any], versions: dict[str, int], answered: list[str] | None = None) -> AskSummary:
    scope = ask.get("scope") or {}
    source = ask.get("source_run_id") or ""
    return AskSummary(
        id=ask["id"], question=ask.get("question") or "", mode=ask.get("mode") or "independent",
        scope=AskScope(kind=scope.get("kind") or "record", issue=scope.get("issue"), label=scope.get("label") or "Whole record"),
        status=_ask_status(ask, answered if answered is not None else ask.get("answered")),
        runId=source, version=ask.get("source_version") or versions.get(source),
        createdAt=_iso(ask.get("created_at")), finishedAt=_iso(ask.get("finished_at")) or None,
    )


@router.post("/cases/{case_id}/asks", response_model=AskView, status_code=status.HTTP_202_ACCEPTED)
async def create_ask(case_id: CaseId, body: AskRequest, c: C) -> AskView:
    """Ask the council a question, grounded on one finished report version (default: the published one).

    The question runs on the same durable engine as the analysis (leases, retries, recovery);
    poll ``GET /asks/{askId}`` while it is running.
    """
    case = await _case_or_404(c, case_id)
    configured = c.orchestrator.council_ids()
    if not configured:
        raise HTTPException(status.HTTP_409_CONFLICT, "The model council is not configured")
    members = list(dict.fromkeys(body.members)) if body.members else configured
    unknown = [m for m in members if m not in configured]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown council member: {', '.join(unknown)}")
    if body.mode == "debate" and len(members) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Debate needs at least two council members")

    source = body.runId or case.get("report_run_id") or await c.repo.legacy_report_run(case_id)
    src = await c.repo.get_run(case_id, source) if source else None
    issues = await c.repo.get_report(case_id, "issues", source) if src and src.get("status") in ("succeeded", "partial") else None
    if not issues:
        raise HTTPException(status.HTTP_409_CONFLICT, "That version has no finished report to ask about"
                            if body.runId else "There is no finished report to ask about yet")
    scope: dict[str, Any] = {"kind": "record", "issue": None, "label": "Whole record"}
    if body.scope.kind == "issue":
        n = body.scope.issue
        hit = next((i for i in (issues.get("data") or {}).get("issues") or [] if n is not None and i.get("n") == n), None)
        if not hit:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Choose an issue from this version" if n is None else f"Issue {n} is not in this version")
        scope = {"kind": "issue", "issue": n, "label": f"Issue {n} · {hit.get('topic') or 'Untitled'}"[:160]}

    limit = c.settings.ask_max_running_per_case
    if len(await c.repo.running_asks(case_id)) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"{limit} questions are already running for this case. Wait for one to finish.")
    _, versions = await _versions(c, case_id)
    ask_id = await c.orchestrator.start_ask(
        case_id, question=body.question, mode=body.mode, scope=scope, members=members, source_run_id=source,
        source_version=versions.get(source),
    )
    return await _ask_view(c, case_id, ask_id)


@router.get("/cases/{case_id}/asks", response_model=list[AskSummary])
async def list_asks(case_id: CaseId, c: C) -> list[AskSummary]:
    await _case_or_404(c, case_id)
    asks = await c.repo.list_asks(case_id)
    versions = {} if all(a.get("source_version") for a in asks) else (await _versions(c, case_id))[1]
    for a in asks:
        _maybe_reconcile_ask(c, case_id, a)
    return [_ask_summary(a, versions) for a in asks]


@router.get("/cases/{case_id}/asks/{ask_id}", response_model=AskView)
async def get_ask(case_id: CaseId, ask_id: AskId, c: C) -> AskView:
    await _case_or_404(c, case_id)
    return await _ask_view(c, case_id, ask_id)


async def _ask_view(c: Container, case_id: str, ask_id: str) -> AskView:
    ask = await c.repo.get_run(case_id, ask_id)
    if not ask:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    _maybe_reconcile_ask(c, case_id, ask)
    steps = await c.repo.list_steps(case_id, ask_id)
    by_id = {s["id"]: s for s in steps}
    outs = await _outputs(c, steps)
    members = list(ask.get("council_models") or [])
    mode = ask.get("mode") or "independent"

    answers = []
    for mid in members:
        st, o = by_id.get(f"answer--{mid}"), outs.get(f"answer--{mid}") or {}
        state = _step_state(st)
        answers.append(AskAnswerOut(
            member=mid, status=state, model=o.get("model"), error=_step_error(st, o, state),
            paragraphs=o.get("paragraphs") or [], turnsOnDisputedFact=bool(o.get("turnsOnDisputedFact")),
            cites=o.get("cites") or [], claimant=o.get("claimant") or [], defendant=o.get("defendant") or [],
        ))
    reviews = []
    if mode == "debate":
        for mid in members:
            st, o = by_id.get(f"review--{mid}"), outs.get(f"review--{mid}") or {}
            state = _step_state(st)
            reviews.append(AskReviewOut(
                member=mid, status=state, error=_step_error(st, o, state), notes=o.get("notes") or [], revised=o.get("revised") or "",
            ))
    st, o = by_id.get("synth"), outs.get("synth") or {}
    state = _step_state(st)
    synthesis = SynthesisOut(
        status=state, chair=o.get("chair"), model=o.get("model"), error=_step_error(st, o, state),
        summary=o.get("summary") or "", agree=o.get("agree") or [], differ=o.get("differ") or [], leftOut=o.get("leftOut") or [],
    )
    steelman = SteelmanOut(**o["steelman"]) if mode == "steelman" and o.get("steelman") else None
    answered = [a.member for a in answers if a.status == "succeeded"] if ask.get("status") != "running" else None
    summary = _ask_summary(ask, {}, answered)
    return AskView(
        **summary.model_dump(), members=members, answers=answers, reviews=reviews, synthesis=synthesis, steelman=steelman,
    )
