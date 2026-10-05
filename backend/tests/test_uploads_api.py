"""Upload API: atomic link creation, guarded complete/abandon transitions and the automatic start.

The API runs against in-memory fakes of Firestore, Cloud Storage and the orchestrator, so these
tests pin the state machine (pending_upload -> uploaded | rejected | abandoned) without GCP.
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("VTX_PROJECT_ID", "test-project")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes  # noqa: E402
from app.api.routes import router  # noqa: E402
from app.storage.firestore import now  # noqa: E402

CASE = "c0123456789ab"
PDF = b"%PDF-1.7\n" + b"x" * 100


class FakeRepo:
    def __init__(self) -> None:
        self.cases: dict[str, dict[str, Any]] = {CASE: {"id": CASE, "draft": True, "status": "queued"}}  # as POST /cases
        self.docs: dict[str, dict[str, Any]] = {}
        self.batches = 0

    async def get_case(self, case_id: str) -> dict[str, Any] | None:
        return dict(self.cases[case_id]) if case_id in self.cases else None

    async def update_case(self, case_id: str, data: dict[str, Any]) -> None:
        self.cases[case_id].update({**data, "updated_at": now()})

    async def create_documents(self, case_id: str, docs: dict[str, dict[str, Any]]) -> None:
        self.batches += 1
        ts = now()
        for i, (doc_id, data) in enumerate(docs.items()):
            self.docs[doc_id] = {"id": doc_id, **data, "created_at": ts + timedelta(microseconds=i)}

    async def get_document(self, case_id: str, doc_id: str) -> dict[str, Any] | None:
        d = self.docs.get(doc_id)
        return dict(d) if d else None

    async def list_documents(self, case_id: str) -> list[dict[str, Any]]:
        return sorted((dict(d) for d in self.docs.values()), key=lambda d: d["created_at"])

    async def transition_document(self, case_id: str, doc_id: str, expect: str, data: dict[str, Any]) -> dict[str, Any] | None:
        d = self.docs.get(doc_id)
        if not d or d.get("status") != expect:
            return None
        d.update(data)
        return dict(d)


class FakeGcs:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.in_flight = self.max_in_flight = self.calls = 0
        self.fail_on_call: int | None = None

    async def signed_put_url(self, object_name: str, content_type: str, max_bytes: int) -> tuple[str, dict[str, str]]:
        self.calls += 1
        call = self.calls
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)
            if call == self.fail_on_call:
                raise RuntimeError("signBlob unavailable")
            return f"https://signed.example/{object_name}", {"Content-Type": content_type, "x-goog-content-length-range": f"1,{max_bytes}"}
        finally:
            self.in_flight -= 1

    async def stat(self, bucket: str, name: str) -> dict[str, Any] | None:
        o = self.objects.get(name)
        return None if o is None else {"size": len(o), "generation": 7, "crc32c": "AAAAAA==", "content_type": "application/pdf"}

    async def read_head(self, bucket: str, name: str, n: int = 8192) -> bytes:
        return self.objects[name][:n]

    async def delete(self, bucket: str, name: str) -> None:
        self.deleted.append(name)
        self.objects.pop(name, None)


class FakeOrchestrator:
    def __init__(self) -> None:
        self.started: list[tuple[str, str, str | None]] = []

    async def start_run(self, case_id: str, trigger: str, idem_key: str | None = None) -> str:
        self.started.append((case_id, trigger, idem_key))
        return "r0123456789ab"


def make_api() -> tuple[TestClient, FakeRepo, FakeGcs, FakeOrchestrator]:
    repo, gcs, orch = FakeRepo(), FakeGcs(), FakeOrchestrator()
    settings = SimpleNamespace(case_bucket="case-files", max_files_per_upload=50, max_upload_bytes=500 * 2**20,
                               upload_url_ttl_s=900, stale_run_seconds=600)
    app = FastAPI()
    app.include_router(router)
    app.state.container = SimpleNamespace(settings=settings, repo=repo, gcs=gcs, orchestrator=orch)
    return TestClient(app, raise_server_exceptions=False), repo, gcs, orch


def request_links(api: TestClient, *names: str) -> list[dict[str, Any]]:
    files = [{"name": n, "size": len(PDF), "contentType": "application/pdf"} for n in names]
    r = api.post(f"/api/v1/cases/{CASE}/uploads", json={"files": files})
    assert r.status_code == 200, r.text
    return r.json()["targets"]


def land(repo: FakeRepo, gcs: FakeGcs, doc_id: str, body: bytes = PDF) -> None:
    """Simulate the browser's PUT to the signed URL."""
    gcs.objects[repo.docs[doc_id]["object_name"]] = body


def test_links_are_signed_concurrently_and_records_created_in_one_batch_in_order():
    api, repo, gcs, _ = make_api()
    names = [f"bundle-{i}.pdf" for i in range(8)]
    targets = request_links(api, *names)
    assert [t["name"] for t in targets] == names
    assert gcs.max_in_flight > 1, "links should be signed concurrently"
    assert repo.batches == 1
    listed = [d["name"] for d in asyncio.run(repo.list_documents(CASE))]
    assert listed == names, "documents keep the order the files were picked"
    assert all(d["status"] == "pending_upload" for d in repo.docs.values())
    assert len({t["uploadUrl"] for t in targets}) == 8


def test_a_failed_signature_creates_no_records():
    api, repo, gcs, _ = make_api()
    gcs.fail_on_call = 3
    r = api.post(f"/api/v1/cases/{CASE}/uploads", json={"files": [
        {"name": f"f{i}.pdf", "size": 10, "contentType": "application/pdf"} for i in range(5)]})
    assert r.status_code == 500
    assert repo.docs == {}, "no orphan pending records may hold back the analysis"


def test_analysis_starts_only_after_the_last_pending_upload_is_completed_or_abandoned():
    api, repo, gcs, orch = make_api()
    a, b = request_links(api, "a.pdf", "b.pdf")
    land(repo, gcs, a["documentId"])
    r = api.post(f"/api/v1/cases/{CASE}/documents/{a['documentId']}/complete")
    assert r.status_code == 200 and r.json()["status"] == "uploaded"
    assert orch.started == [], "b.pdf is still pending"

    r = api.post(f"/api/v1/cases/{CASE}/documents/{b['documentId']}/abandon")
    assert r.status_code == 200 and r.json()["status"] == "abandoned"
    assert len(orch.started) == 1 and orch.started[0][1] == "upload"
    assert repo.docs[b["documentId"]]["object_name"] in gcs.deleted

    # Idempotent: abandoning again changes nothing and starts nothing new.
    assert api.post(f"/api/v1/cases/{CASE}/documents/{b['documentId']}/abandon").status_code == 200
    assert len(orch.started) == 1


def test_abandon_cannot_undo_an_upload_and_complete_cannot_revive_an_abandoned_one():
    api, repo, gcs, _ = make_api()
    a, b = request_links(api, "a.pdf", "b.pdf")
    land(repo, gcs, a["documentId"])
    assert api.post(f"/api/v1/cases/{CASE}/documents/{a['documentId']}/complete").status_code == 200
    r = api.post(f"/api/v1/cases/{CASE}/documents/{a['documentId']}/abandon")
    assert r.status_code == 409
    assert repo.docs[a["documentId"]]["status"] == "uploaded"

    assert api.post(f"/api/v1/cases/{CASE}/documents/{b['documentId']}/abandon").status_code == 200
    land(repo, gcs, b["documentId"])  # a late PUT on the old link
    r = api.post(f"/api/v1/cases/{CASE}/documents/{b['documentId']}/complete")
    assert r.status_code == 409
    assert repo.docs[b["documentId"]]["status"] == "abandoned"


def test_complete_is_idempotent_and_rejects_mismatched_content():
    api, repo, gcs, _ = make_api()
    good, bad = request_links(api, "good.pdf", "bad.pdf")
    land(repo, gcs, good["documentId"])
    first = api.post(f"/api/v1/cases/{CASE}/documents/{good['documentId']}/complete")
    again = api.post(f"/api/v1/cases/{CASE}/documents/{good['documentId']}/complete")
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()

    land(repo, gcs, bad["documentId"], b"PK\x03\x04 not a pdf" + b"x" * 64)
    r = api.post(f"/api/v1/cases/{CASE}/documents/{bad['documentId']}/complete")
    assert r.status_code == 422 and "does not match" in r.json()["detail"]
    assert repo.docs[bad["documentId"]]["status"] == "rejected"
    assert repo.docs[bad["documentId"]]["object_name"] in gcs.deleted
    # A rejected file is closed: abandoning it is a no-op, not an error.
    assert api.post(f"/api/v1/cases/{CASE}/documents/{bad['documentId']}/abandon").status_code == 200


def test_unknown_documents_and_bad_ids_are_refused():
    api, *_ = make_api()
    assert api.post(f"/api/v1/cases/{CASE}/documents/d0123456789ab/abandon").status_code == 404
    assert api.post(f"/api/v1/cases/{CASE}/documents/../abandon").status_code in (404, 422)
    assert api.post(f"/api/v1/cases/{CASE}/documents/dZZZ/abandon").status_code == 422


def read_case(api: TestClient) -> None:
    """Run the self-healing read path (as GET /cases and GET /cases/{id} do) and wait for what it spawns."""
    container = api.app.state.container

    async def go() -> None:
        before = set(routes._background)
        await routes._maybe_reconcile(container, await container.repo.get_case(CASE))
        await asyncio.gather(*(routes._background - before))

    asyncio.run(go())


def test_a_batch_cut_short_by_a_closed_tab_starts_on_a_later_read():
    """One file landed, then the tab closed: the other link expires and nothing is left to
    complete. A later read of the case starts the analysis, once the links are stale."""
    api, repo, gcs, orch = make_api()
    a, _ = request_links(api, "a.pdf", "b.pdf")
    land(repo, gcs, a["documentId"])
    assert api.post(f"/api/v1/cases/{CASE}/documents/{a['documentId']}/complete").status_code == 200
    read_case(api)
    assert orch.started == [], "b.pdf may still be uploading"

    long_ago = now() - timedelta(minutes=17)
    repo.cases[CASE]["updated_at"] = long_ago
    for d in repo.docs.values():
        d["created_at"] = long_ago
    read_case(api)
    assert len(orch.started) == 1 and orch.started[0][1] == "upload"


def test_a_later_read_never_starts_a_draft_or_cuts_off_a_fresh_upload():
    api, repo, gcs, orch = make_api()
    a, _ = request_links(api, "a.pdf", "b.pdf")
    repo.cases[CASE]["updated_at"] = now() - timedelta(minutes=17)
    read_case(api)
    assert orch.started == [], "nothing has been uploaded yet: the case is still a draft"

    land(repo, gcs, a["documentId"])
    assert api.post(f"/api/v1/cases/{CASE}/documents/{a['documentId']}/complete").status_code == 200
    repo.cases[CASE]["updated_at"] = now() - timedelta(minutes=17)
    read_case(api)
    assert orch.started == [], "b.pdf's link is still valid, so it may still be uploading"
