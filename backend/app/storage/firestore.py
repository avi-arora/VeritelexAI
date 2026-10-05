"""Firestore access layer.

Layout::

    cases/{caseId}
    cases/{caseId}/documents/{docId}
    cases/{caseId}/runs/{runId}                      analysis runs ("r…"), one per report version
    cases/{caseId}/runs/{runId}/steps/{stepId}
    cases/{caseId}/runs/{runId}/report/{section}     the report of that version (never overwritten)
    cases/{caseId}/asks/{askId}                      "Ask the council" runs ("q…"), same engine
    cases/{caseId}/asks/{askId}/steps/{stepId}
    cases/{caseId}/report/{section}                  legacy: reports written before versioning

All values written here are produced by the server; client input is
validated by Pydantic before it reaches this module.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_transaction import AsyncTransaction

from app.config import Settings


def now() -> datetime:
    return datetime.now(UTC)


def _report(snap: Any) -> dict[str, Any] | None:
    if not snap.exists:
        return None
    doc = snap.to_dict()
    doc["data"] = json.loads(doc.pop("json")) if "json" in doc else doc.get("data")
    return doc


class Repo:
    def __init__(self, settings: Settings, client: AsyncClient | None = None):
        self.db = client or firestore.AsyncClient(project=settings.project_id, database=settings.firestore_database)

    # ------------------------------------------------------------ refs
    def case_ref(self, case_id: str):
        return self.db.collection("cases").document(case_id)

    def doc_ref(self, case_id: str, doc_id: str):
        return self.case_ref(case_id).collection("documents").document(doc_id)

    def run_ref(self, case_id: str, run_id: str):
        # Ask runs ("q…") live apart from analysis runs ("r…") but share the engine and step layout.
        col = "asks" if run_id.startswith("q") else "runs"
        return self.case_ref(case_id).collection(col).document(run_id)

    def step_ref(self, case_id: str, run_id: str, step_id: str):
        return self.run_ref(case_id, run_id).collection("steps").document(step_id)

    def report_ref(self, case_id: str, section: str):
        """Legacy (pre-versioning) report location, read-only fallback."""
        return self.case_ref(case_id).collection("report").document(section)

    def run_report_ref(self, case_id: str, run_id: str, section: str):
        return self.run_ref(case_id, run_id).collection("report").document(section)

    def transaction(self) -> AsyncTransaction:
        return self.db.transaction(max_attempts=10)

    # ------------------------------------------------------------ cases
    async def create_case(self, case_id: str, data: dict[str, Any]) -> None:
        ts = now()
        await self.case_ref(case_id).create({**data, "created_at": ts, "updated_at": ts})

    async def get_case(self, case_id: str) -> dict[str, Any] | None:
        snap = await self.case_ref(case_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    async def update_case(self, case_id: str, data: dict[str, Any]) -> None:
        await self.case_ref(case_id).set({**data, "updated_at": now()}, merge=True)

    async def list_cases(self, limit: int = 200) -> list[dict[str, Any]]:
        q = self.db.collection("cases").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    # ------------------------------------------------------------ documents
    async def create_document(self, case_id: str, doc_id: str, data: dict[str, Any]) -> None:
        await self.doc_ref(case_id, doc_id).create({**data, "created_at": now()})

    async def create_documents(self, case_id: str, docs: dict[str, dict[str, Any]]) -> None:
        """Create several document records in one atomic batch: all of them or none."""
        batch = self.db.batch()
        ts = now()
        for i, (doc_id, data) in enumerate(docs.items()):
            # Distinct timestamps keep list_documents() in the order the files were picked.
            batch.create(self.doc_ref(case_id, doc_id), {**data, "created_at": ts + timedelta(microseconds=i)})
        await batch.commit()

    async def get_document(self, case_id: str, doc_id: str) -> dict[str, Any] | None:
        snap = await self.doc_ref(case_id, doc_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    async def update_document(self, case_id: str, doc_id: str, data: dict[str, Any]) -> None:
        await self.doc_ref(case_id, doc_id).set({**data, "updated_at": now()}, merge=True)

    async def transition_document(
        self, case_id: str, doc_id: str, expect: str, data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply ``data`` atomically, but only while the document's status is still ``expect``.

        Returns the updated document, or ``None`` if it is missing or has already moved on,
        so of two racing requests (e.g. complete and abandon) exactly one wins.
        """
        ref = self.doc_ref(case_id, doc_id)

        @firestore.async_transactional
        async def txn(transaction: AsyncTransaction) -> dict[str, Any] | None:
            snap = await ref.get(transaction=transaction)
            current = snap.to_dict() if snap.exists else None
            if not current or current.get("status") != expect:
                return None
            upd = {**data, "updated_at": now()}
            transaction.set(ref, upd, merge=True)
            return {"id": snap.id, **current, **upd}

        return await txn(self.transaction())

    async def list_documents(self, case_id: str) -> list[dict[str, Any]]:
        q = self.case_ref(case_id).collection("documents").order_by("created_at")
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    # ------------------------------------------------------------ runs / steps
    async def get_run(self, case_id: str, run_id: str) -> dict[str, Any] | None:
        snap = await self.run_ref(case_id, run_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    async def find_run_by_key(self, case_id: str, idem_key: str) -> dict[str, Any] | None:
        q = self.case_ref(case_id).collection("runs").where(filter=firestore.FieldFilter("idem_key", "==", idem_key)).limit(1)
        async for s in q.stream():
            return {"id": s.id, **s.to_dict()}
        return None

    async def update_run(self, case_id: str, run_id: str, data: dict[str, Any]) -> None:
        await self.run_ref(case_id, run_id).set({**data, "updated_at": now()}, merge=True)

    async def list_steps(self, case_id: str, run_id: str, transaction: AsyncTransaction | None = None) -> list[dict[str, Any]]:
        col = self.run_ref(case_id, run_id).collection("steps")
        stream = col.stream(transaction=transaction) if transaction else col.stream()
        return [{"id": s.id, **s.to_dict()} async for s in stream]

    async def get_step(self, case_id: str, run_id: str, step_id: str) -> dict[str, Any] | None:
        snap = await self.step_ref(case_id, run_id, step_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    async def update_step(self, case_id: str, run_id: str, step_id: str, data: dict[str, Any]) -> None:
        await self.step_ref(case_id, run_id, step_id).set({**data, "updated_at": now()}, merge=True)

    async def list_runs(self, case_id: str) -> list[dict[str, Any]]:
        """Every analysis run of the case, oldest first (the order defines version numbers)."""
        q = self.case_ref(case_id).collection("runs").order_by("created_at")
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    async def list_steps_of(self, case_id: str, run_id: str, spec: str) -> list[dict[str, Any]]:
        """Steps of one spec (single-field equality, so the automatic index serves it)."""
        q = self.run_ref(case_id, run_id).collection("steps").where(filter=firestore.FieldFilter("spec", "==", spec))
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    async def list_asks(self, case_id: str, limit: int = 50) -> list[dict[str, Any]]:
        q = self.case_ref(case_id).collection("asks").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    async def running_asks(self, case_id: str) -> list[dict[str, Any]]:
        q = self.case_ref(case_id).collection("asks").where(filter=firestore.FieldFilter("status", "==", "running"))
        return [{"id": s.id, **s.to_dict()} async for s in q.stream()]

    # ------------------------------------------------------------ report
    async def put_report(self, case_id: str, section: str, run_id: str, data: dict[str, Any]) -> None:
        # Stored as a JSON string: report shapes contain nested arrays (e.g. coverage tuples),
        # which Firestore cannot store natively. Sections are small (well under the 1 MiB doc limit).
        # Each run writes under its own path, so earlier versions stay intact.
        payload = json.dumps(data, ensure_ascii=False, default=str)
        await self.run_report_ref(case_id, run_id, section).set({"run_id": run_id, "json": payload, "updated_at": now()})

    async def get_report(self, case_id: str, section: str, run_id: str | None = None) -> dict[str, Any] | None:
        """The section of report version ``run_id``; the legacy location serves runs from before versioning."""
        if run_id:
            doc = _report(await self.run_report_ref(case_id, run_id, section).get())
            if doc:
                return doc
        legacy = _report(await self.report_ref(case_id, section).get())
        if legacy and (run_id is None or legacy.get("run_id") == run_id):
            return legacy
        return None

    async def legacy_report_run(self, case_id: str) -> str | None:
        snap = await self.report_ref(case_id, "background").get()
        return (snap.to_dict() or {}).get("run_id") if snap.exists else None
