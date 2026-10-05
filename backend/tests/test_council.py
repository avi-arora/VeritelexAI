"""Model council, report versions and "ask the council": agents, engine and API.

Everything runs against an in-memory store that plays Firestore and Cloud Storage, and a fake
council whose members answer from canned replies (or raise). These tests pin the comparison and
voting logic, the degraded paths (a member not enabled in Model Garden, a failing chair, nobody
answering) and the API contract (``council_api_contract.md``) without GCP.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("VTX_PROJECT_ID", "test-project")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.ask import SynthAgent, _tokens  # noqa: E402
from app.agents.base import AgentContext  # noqa: E402
from app.agents.corpus import citation_index, labelled  # noqa: E402
from app.agents.council import ConsensusAgent, CouncilMemberAgent, council_sections  # noqa: E402
from app.agents.record import Authority, RecordView, check_cite  # noqa: E402
from app.api import routes  # noqa: E402
from app.harness.dag import PIPELINE  # noqa: E402
from app.harness.engine import Orchestrator  # noqa: E402
from app.harness.llm import Grounding, LLMResult  # noqa: E402
from app.harness.resilience import PermanentStepError, RetryableStepError, UnavailableError  # noqa: E402

CASE = "c0123456789ab"
R1, R2, R3 = "r100000000001", "r200000000002", "r300000000003"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
ISSUES = [{"n": 1, "topic": "Notice"}, {"n": 2, "topic": "Delay"}]
NOT_ENABLED = "Not enabled in Model Garden for this project"


# ====================================================================== fakes
class Store:
    """In-memory Firestore (case, runs, asks, steps, report sections) and Cloud Storage (step outputs)."""

    def __init__(self) -> None:
        self.case: dict[str, Any] = {"id": CASE, "title": "Alpha v Beta", "status": "ready", "updated_at": datetime.now(UTC)}
        self.runs: dict[str, dict[str, Any]] = {}  # "r…" analysis runs and "q…" asks, in creation order
        self.steps: dict[str, dict[str, dict[str, Any]]] = {}
        self.objects: dict[str, Any] = {}
        self.reports: dict[tuple[str, str], Any] = {}
        self.legacy: dict[str, tuple[str, Any]] = {}

    def add_step(self, run_id: str, spec: str, key: str | None = None, status: str = "succeeded",
                 output: Any = None, **extra: Any) -> None:
        sid = f"{spec}--{key}" if key else spec
        st = {"id": sid, "spec": spec, "key": key, "agent": spec, "status": status, "critical": False, "attempts": 1, **extra}
        if output is not None:
            st["output_uri"] = f"gs://artifacts/{run_id}/{sid}.json"
            self.objects[st["output_uri"]] = output
        self.steps.setdefault(run_id, {})[sid] = st

    # ---- Firestore
    async def get_case(self, case_id: str) -> dict[str, Any] | None:
        return dict(self.case) if case_id == CASE else None

    async def update_case(self, case_id: str, data: dict[str, Any]) -> None:
        self.case.update(data)

    async def get_run(self, case_id: str, run_id: str) -> dict[str, Any] | None:
        r = self.runs.get(run_id)
        return {"id": run_id, **r} if r is not None else None

    async def update_run(self, case_id: str, run_id: str, data: dict[str, Any]) -> None:
        self.runs.setdefault(run_id, {}).update(data)

    async def list_runs(self, case_id: str) -> list[dict[str, Any]]:
        return [{"id": k, **v} for k, v in self.runs.items() if k.startswith("r")]

    async def list_asks(self, case_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return [{"id": k, **v} for k, v in reversed(self.runs.items()) if k.startswith("q")][:limit]

    async def running_asks(self, case_id: str) -> list[dict[str, Any]]:
        return [a for a in await self.list_asks(case_id) if a.get("status") == "running"]

    async def list_steps(self, case_id: str, run_id: str, transaction: Any = None) -> list[dict[str, Any]]:
        return [dict(s) for s in self.steps.get(run_id, {}).values()]

    async def list_steps_of(self, case_id: str, run_id: str, spec: str) -> list[dict[str, Any]]:
        return [s for s in await self.list_steps(case_id, run_id) if s["spec"] == spec]

    async def get_step(self, case_id: str, run_id: str, step_id: str) -> dict[str, Any] | None:
        s = self.steps.get(run_id, {}).get(step_id)
        return dict(s) if s else None

    async def get_report(self, case_id: str, section: str, run_id: str | None = None) -> dict[str, Any] | None:
        if run_id and (run_id, section) in self.reports:
            return {"run_id": run_id, "updated_at": T0, "data": self.reports[(run_id, section)]}
        legacy = self.legacy.get(section)
        if legacy and (run_id is None or legacy[0] == run_id):
            return {"run_id": legacy[0], "updated_at": T0, "data": legacy[1]}
        return None

    async def legacy_report_run(self, case_id: str) -> str | None:
        return self.legacy["background"][0] if "background" in self.legacy else None

    # ---- Cloud Storage
    async def read_json(self, uri: str) -> Any:
        return self.objects[uri]


class FakeCouncil:
    """Members answer from canned replies; an exception in ``replies`` is raised instead."""

    def __init__(self, replies: dict[str, Any] | None = None, members: tuple[str, ...] = ("gemini", "claude", "grok")):
        self.members = {
            mid: SimpleNamespace(id=mid, name=mid.title(), mono=mid[:2].title(), color="#334455", max_input_chars=1_000_000)
            for mid in members
        }
        self.replies = replies or {}
        self.calls: list[str] = []

    def member(self, mid: str) -> Any:
        return self.members[mid]

    def chair_order(self, prefer: Any = ()) -> list[str]:
        first = set(prefer)
        return [m for m in self.members if m in first] + [m for m in self.members if m not in first]

    async def generate(self, member_id: str, *, schema: Any, system: str, contents: list[str], temperature: float = 0.2,
                       max_output_tokens: int | None = None) -> LLMResult[Any]:
        self.calls.append(member_id)
        reply = self.replies[member_id]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(data=schema.model_validate(reply), model=f"{member_id}-model", usage={}, grounding=Grounding())


def agent_ctx(store: Store, council: FakeCouncil, run_id: str, spec: str = "consensus", key: str | None = None) -> AgentContext:
    step = {"id": f"{spec}--{key}" if key else spec, "spec": spec, "key": key}
    return AgentContext(CASE, run_id, step, store, store, None, SimpleNamespace(ask_corpus_chars=800_000), council=council)  # type: ignore[arg-type]


def reading(issue: int, text: str) -> dict[str, Any]:
    return {"issue": issue, "reading": text, "turns_on": "the date notice was given", "confidence": "medium", "cites": []}


def read_by(mid: str, readings: list[dict[str, Any]], flagged: list[dict[str, Any]] | None = None,
            questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"member": mid, "name": mid.title(), "status": "succeeded", "model": f"{mid}-model",
            "readings": readings, "flagged": flagged or [], "questions": questions or []}


def unavailable(mid: str) -> dict[str, Any]:
    return {"member": mid, "name": mid.title(), "status": "unavailable", "model": None, "detail": NOT_ENABLED,
            "readings": [], "flagged": [], "questions": []}


# ====================================================================== council members
def test_a_member_not_enabled_in_model_garden_is_recorded_as_unavailable_not_failed():
    store = Store()
    store.runs["r1"] = {"doc_ids": []}
    store.add_step("r1", "issues", output={"issues": [{"n": 1, "topic": "Notice", "question": "Was notice given?"}]})
    council = FakeCouncil({"claude": UnavailableError("claude-opus-5-5: 404", user_message="Claude is not enabled")})
    res = asyncio.run(CouncilMemberAgent().run(agent_ctx(store, council, "r1", spec="council", key="claude")))
    assert res.outcome == "unavailable"
    assert res.output["status"] == "unavailable" and res.output["readings"] == [] and res.output["detail"] == NOT_ENABLED


def test_a_missing_permission_is_not_reported_as_a_model_to_enable_in_model_garden():
    import httpx
    from pydantic import BaseModel

    from app.config import Settings
    from app.harness.council import CouncilLLM
    from app.harness.providers import NOT_ENABLED as NOT_ENABLED_REASON
    from app.harness.providers import ModelUnavailable, _classify

    not_enabled = httpx.Response(404, text='{"error": {"code": 404, "message": "Publisher model `projects/p/locations/global/'
                                          'publishers/anthropic/models/claude-opus-5-5` was not found or your project does '
                                          'not have access to it."}}')
    denied = httpx.Response(403, text='{"error": {"code": 403, "message": "Permission \'aiplatform.endpoints.predict\' denied '
                                      'on resource (or it may not exist).", "status": "PERMISSION_DENIED", '
                                      '"details": [{"reason": "IAM_PERMISSION_DENIED"}]}}')

    def reason(resp: httpx.Response) -> str:
        exc = _classify(resp, "claude-opus-5-5")
        assert isinstance(exc, ModelUnavailable)
        return exc.reason

    assert reason(not_enabled) == NOT_ENABLED_REASON
    assert "roles/aiplatform.user" in reason(denied)

    class Out(BaseModel):
        ok: bool

    class Rest:
        def __init__(self, resp: httpx.Response):
            self.resp = resp

        async def call(self, *args: Any, **kwargs: Any) -> Any:
            raise _classify(self.resp, "model")

        async def ping(self, *args: Any, **kwargs: Any) -> None:
            raise _classify(self.resp, "model")

        async def aclose(self) -> None:
            pass

    async def go(resp: httpx.Response) -> tuple[UnavailableError, dict[str, Any]]:
        council = CouncilLLM(Settings(project_id="test-project"), gemini=None, rest=Rest(resp))  # type: ignore[arg-type]
        with pytest.raises(UnavailableError) as err:
            await council.generate("claude", schema=Out, system="s", contents=["record"])
        return err.value, await council.probe("grok", force=True)

    err, probe = asyncio.run(go(denied))
    assert "roles/aiplatform.user" in err.detail and "Model Garden" not in err.detail
    assert probe["status"] == "unavailable" and "roles/aiplatform.user" in probe["detail"]
    err, probe = asyncio.run(go(not_enabled))
    assert err.detail == NOT_ENABLED and NOT_ENABLED_REASON in probe["detail"]



def test_member_readings_keep_only_known_issues_and_every_citation_is_checked():
    store = Store()
    store.runs["r1"] = {"doc_ids": ["d1"]}
    store.add_step("r1", "ingest", "d1", output={
        "label": "Contract", "doc_type": "Contract", "segments": [{"ref": "p. 12", "text": "Notice shall be given within 14 days."}],
    })
    store.add_step("r1", "issues", output={"issues": [{"n": 1, "topic": "Notice", "question": "Was notice given?"}]})
    cites = [{"kind": "record", "text": "Contract, p. 12"}, {"kind": "authority", "text": "Made Up v Nobody [2020] DIFC CFI 9"}]
    council = FakeCouncil({"gemini": {
        "readings": [
            {"issue": 1, "reading": "Notice is a condition precedent.", "turns_on": "The 14 March letter", "confidence": "high", "cites": cites},
            {"issue": 1, "reading": "A second reading of the same issue.", "turns_on": "-", "confidence": "low", "cites": []},
            {"issue": 5, "reading": "An issue the analysis never identified.", "turns_on": "-", "confidence": "low", "cites": []},
        ],
        "flagged": [{"text": "Notice was late", "ref": "Contract, p. 12"}],
        "questions": [{"to": "Claimant", "question": "When was notice sent?", "why": "Timing decides it", "issue": 5, "ref": ""}],
    }})
    out = asyncio.run(CouncilMemberAgent().run(agent_ctx(store, council, "r1", spec="council", key="gemini"))).output
    assert [r["issue"] for r in out["readings"]] == [1]
    assert [c["status"] for c in out["readings"][0]["cites"]] == ["verified", "bad"]
    assert out["flagged"][0]["check"] == "verified"
    assert out["questions"][0]["issue"] == 0  # an issue number the analysis does not know is not trusted


# ====================================================================== consensus
def test_consensus_is_skipped_when_no_member_produced_a_reading():
    store, council = Store(), FakeCouncil()
    store.add_step("r1", "council", "gemini", output=unavailable("gemini"), outcome="unavailable")
    store.add_step("r1", "council", "claude", status="failed", user_error="Claude could not answer")
    res = asyncio.run(ConsensusAgent().run(agent_ctx(store, council, "r1")))
    assert res.outcome == "skipped" and res.output["compared"] is False
    assert council.calls == []


def test_a_single_reading_needs_no_chair():
    store, council = Store(), FakeCouncil()
    store.add_step("r1", "council", "claude", output=read_by(
        "claude", [reading(1, "Clause 20.1 is a condition precedent.")],
        flagged=[{"text": "No notice was sent", "ref": "Contract, p. 3", "check": "verified"}],
    ))
    store.add_step("r1", "council", "grok", output=unavailable("grok"), outcome="unavailable")
    out = asyncio.run(ConsensusAgent().run(agent_ctx(store, council, "r1"))).output
    assert out["compared"] is True and out["chair"] is None
    assert out["issues"] == [{"issue": 1, "positions": [{"text": "Clause 20.1 is a condition precedent.", "members": ["claude"]}]}]
    assert out["flagged"][0]["members"] == ["claude"]
    assert council.calls == []


def test_the_chair_falls_back_to_the_next_member_and_its_grouping_is_sanitised():
    store = Store()
    store.add_step("r1", "issues", output={"issues": ISSUES})
    store.add_step("r1", "council", "gemini", output=read_by(
        "gemini", [reading(1, "G1"), reading(2, "G2")], flagged=[{"text": "Late notice", "ref": "Contract, p. 3", "check": "verified"}],
    ))
    store.add_step("r1", "council", "claude", output=read_by(
        "claude", [reading(1, "C1"), reading(2, "C2")], flagged=[{"text": "late  notice!", "ref": "Contract, p. 3", "check": "verified"}],
    ))
    store.add_step("r1", "council", "grok", output=unavailable("grok"), outcome="unavailable")
    draft = {
        "issues": [
            {"issue": 1, "positions": [
                {"text": "Notice was a condition precedent.", "members": ["claude"]},
                {"text": "Notice was a mere warranty.", "members": ["gemini", "claude", "grok", "nobody"]},
                {"text": "A third view.", "members": ["gemini"]},
            ]},
            {"issue": 1, "positions": [{"text": "The same issue again.", "members": ["gemini"]}]},
            {"issue": 2, "positions": [{"text": "Delay is not excused.", "members": ["gemini", "claude", "grok"]}]},
            {"issue": 7, "positions": [{"text": "An invented issue.", "members": ["gemini"]}]},
        ],
        "flagged": [{"text": "Something only a non-member said", "ref": "", "members": ["grok"]}],
        "questions": [],
    }
    council = FakeCouncil({"gemini": RetryableStepError("quota", "busy"), "claude": draft})
    out = asyncio.run(ConsensusAgent().run(agent_ctx(store, council, "r1"))).output
    assert council.calls == ["gemini", "claude"]  # the first chair failed, the next one compared
    assert out["chair"] == {"id": "claude", "model": "claude-model"}
    assert out["issues"] == [
        {"issue": 1, "positions": [
            {"text": "Notice was a condition precedent.", "members": ["claude"]},
            {"text": "Notice was a mere warranty.", "members": ["gemini"]},  # each member holds one position only
        ]},
        {"issue": 2, "positions": [{"text": "Delay is not excused.", "members": ["gemini", "claude"]}]},
    ]
    # Every flagged item from the chair named only non-members: fall back to the exact-duplicate merge.
    assert out["flagged"] == [{"text": "Late notice", "ref": "Contract, p. 3", "check": "verified", "members": ["gemini", "claude"]}]


def test_consensus_retries_when_no_chair_can_compare():
    store = Store()
    store.add_step("r1", "council", "gemini", output=read_by("gemini", [reading(1, "G1")]))
    store.add_step("r1", "council", "claude", output=read_by("claude", [reading(1, "C1")]))
    council = FakeCouncil({m: RetryableStepError("down", "down") for m in ("gemini", "claude", "grok")})
    with pytest.raises(RetryableStepError):
        asyncio.run(ConsensusAgent().run(agent_ctx(store, council, "r1")))


# ====================================================================== report sections
def seed_council_run(store: Store, consensus: bool = True) -> None:
    store.runs["r1"] = {"council_models": ["gemini", "claude", "grok"]}
    question = {"to": "Claimant", "question": "When was notice sent?", "why": "Decides issue 1", "issue": 1, "ref": "Contract, p. 3"}
    store.add_step("r1", "council", "gemini", output=read_by("gemini", [reading(1, "G1"), reading(2, "G2")], questions=[question]),
                   started_at=T0, finished_at=T0 + timedelta(seconds=40))
    store.add_step("r1", "council", "claude", output=read_by("claude", [reading(1, "C1")]),
                   started_at=T0 + timedelta(seconds=1), finished_at=T0 + timedelta(seconds=50))
    store.add_step("r1", "council", "grok", output=unavailable("grok"), outcome="unavailable",
                   started_at=T0, finished_at=T0 + timedelta(seconds=2))
    if consensus:
        store.add_step("r1", "consensus", output={
            "compared": True, "chair": {"id": "gemini", "model": "gemini-model"},
            "issues": [
                {"issue": 1, "positions": [{"text": "A-reading", "members": ["gemini"]}, {"text": "B-reading", "members": ["claude"]}]},
                {"issue": 2, "positions": [{"text": "Only reading", "members": ["gemini"]}]},
            ],
            "flagged": [{"text": "Late notice", "ref": "Contract, p. 3", "members": ["gemini", "claude"]}],
            "questions": [{**question, "members": ["gemini"]}],
        }, started_at=T0 + timedelta(seconds=50), finished_at=T0 + timedelta(seconds=70))
    else:
        store.add_step("r1", "consensus", status="failed", user_error="The council's readings could not be compared yet")


def test_council_section_votes_notes_and_questions():
    store = Store()
    seed_council_run(store)
    data, questions, summary = asyncio.run(council_sections(agent_ctx(store, FakeCouncil(), "r1"), ISSUES, store.runs["r1"]))
    rows = {r["n"]: r for r in data["rows"]}
    assert (rows[1]["a"], rows[1]["b"]) == ("A-reading", "B-reading")
    assert rows[1]["votes"] == {"gemini": "A", "claude": "B", "grok": "-"}
    assert rows[2]["votes"] == {"gemini": "A", "claude": "-", "grok": "-"} and rows[2]["b"] == ""
    assert [r["member"] for r in rows[1]["readings"]] == ["gemini", "claude"]
    assert data["compared"] is True and data["chair"] == {"id": "gemini", "model": "gemini-model"}
    assert data["durationS"] == 70
    assert "Grok was unavailable" in data["note"]
    assert [(m["id"], m["status"]) for m in data["members"]] == [("gemini", "succeeded"), ("claude", "succeeded"), ("grok", "unavailable")]
    assert data["flagged"] == [{"t": "Late notice", "ref": "Contract, p. 3", "by": ["gemini", "claude"]}]
    assert questions == {"questions": [{
        "id": "q1", "to": "Claimant", "q": "When was notice sent?", "why": "Decides issue 1", "iss": 1, "ref": "Contract, p. 3",
        "by": ["gemini"],
    }]}
    assert summary[2] == {"id": "grok", "status": "unavailable", "model": None, "error": NOT_ENABLED}


def test_without_a_comparison_the_section_shows_each_reading_on_its_own():
    store = Store()
    seed_council_run(store, consensus=False)
    data, _, _ = asyncio.run(council_sections(agent_ctx(store, FakeCouncil(), "r1"), ISSUES, store.runs["r1"]))
    row = next(r for r in data["rows"] if r["n"] == 1)
    assert data["compared"] is False and data["chair"] is None
    assert row["votes"] == {} and row["a"] == "" and row["b"] == ""
    assert len(row["readings"]) == 2
    assert "could not be compared" in data["note"]


def test_versions_made_before_the_council_have_no_council_section():
    store = Store()
    store.runs["r1"] = {}
    assert asyncio.run(council_sections(agent_ctx(store, FakeCouncil(), "r1"), ISSUES, store.runs["r1"])) is None


# ====================================================================== asks
def test_a_single_answer_needs_no_chair_and_the_ask_records_who_answered():
    store = Store()
    store.runs["q1"] = {"source_run_id": "r1", "mode": "independent", "council_models": ["gemini", "claude"]}
    bad = {"kind": "record", "text": "Contract, p. 99", "status": "bad", "note": "Not found in the case record"}
    store.add_step("q1", "answer", "gemini", output={"member": "gemini", "status": "succeeded", "model": "g", "paragraphs": ["Yes."], "cites": [bad]})
    store.add_step("q1", "answer", "claude", output={"member": "claude", "status": "unavailable", "detail": NOT_ENABLED}, outcome="unavailable")
    council = FakeCouncil()
    res = asyncio.run(SynthAgent().run(agent_ctx(store, council, "q1", spec="synth")))
    assert res.output["summary"] == "Only {{m:gemini}} answered, so there is nothing to compare."
    assert res.output["leftOut"] == ["Contract, p. 99 — Not found in the case record"]
    assert store.runs["q1"]["answered"] == ["gemini"]
    assert council.calls == []


def test_a_question_nobody_could_answer_skips_the_synthesis():
    store = Store()
    store.runs["q1"] = {"source_run_id": "r1", "mode": "debate", "council_models": ["gemini", "claude"]}
    for mid in ("gemini", "claude"):
        store.add_step("q1", "answer", mid, output={"member": mid, "status": "unavailable"}, outcome="unavailable")
    res = asyncio.run(SynthAgent().run(agent_ctx(store, FakeCouncil(), "q1", spec="synth")))
    assert res.outcome == "skipped" and store.runs["q1"]["answered"] == []


def test_answer_numbers_become_member_mention_tokens():
    text = "Answer 1 misreads clause 20.1; answer 2 is right. Answer 9 does not exist."
    assert _tokens(text, {1: "claude", 2: "grok"}) == "{{m:claude}} misreads clause 20.1; {{m:grok}} is right. Answer 9 does not exist."


def test_citations_are_checked_against_the_record_and_the_verified_authorities():
    docs = labelled({"d1": {"label": "Contract", "doc_type": "Contract", "segments": [{"ref": "p. 12", "text": "Notice shall be given within 14 days."}]}})
    view = RecordView(
        "r1", {}, docs, [], [{"n": 1, "topic": "Notice"}],
        {1: [Authority("Alpha Ltd v Beta LLC", "[2020] DIFC CFI 001", "Court of First Instance", "2020", "applied", "", False)]},
        {1: ["Gamma Holdings v Delta Trading [2019] DIFC CA 002"]}, citation_index(docs),
    )
    assert check_cite("record", "⟦Contract, p. 12⟧", view)["note"].startswith("Notice shall be given")
    assert check_cite("record", "Contract, p. 99", view)["status"] == "bad"
    assert check_cite("authority", "Alpha Ltd v Beta LLC [2020] DIFC CFI 1", view)["status"] == "verified"
    assert check_cite("authority", "Alpha v Beta", view)["status"] == "verified"
    assert check_cite("authority", "Gamma Holdings v Delta Trading [2019] DIFC CA 2", view)["status"] == "warn"
    assert check_cite("authority", "Invented v Nobody [2021] DIFC CFI 999", view)["status"] == "bad"


# ====================================================================== engine
def orchestrator(store: Store) -> Orchestrator:
    return Orchestrator(settings=SimpleNamespace(), repo=store, gcs=store, llm=None, dag=PIPELINE, agents={}, dispatcher=None)  # type: ignore[arg-type]


def test_a_council_rerun_reuses_the_source_analysis_and_redoes_only_the_council():
    store = Store()
    store.case["report_run_id"] = R2
    store.runs[R2] = {"status": "partial", "doc_ids": ["d1"]}
    for spec, key, status in [("ingest", "d1", "succeeded"), ("issues", None, "succeeded"), ("grounding", "1", "failed"),
                              ("council", "gemini", "succeeded"), ("consensus", None, "succeeded"), ("finalize", None, "succeeded")]:
        store.add_step(R2, spec, key, status=status, output={} if status == "succeeded" else None, lease_owner="w1", created_at=T0)
    steps, materialized, doc_ids, source = asyncio.run(orchestrator(store)._council_rerun_steps(CASE, None, ["gemini", "claude"]))
    by_id = {s["id"]: s for s in steps}
    assert source == R2 and doc_ids == ["d1"]
    reused = by_id["ingest--d1"]
    assert reused["reused_from"] == R2 and reused["status"] == "succeeded" and reused["output_uri"].startswith(f"gs://artifacts/{R2}/")
    assert "lease_owner" not in reused and "created_at" not in reused
    assert by_id["grounding--1"]["status"] == "failed"  # the same gap is carried over, not hidden
    assert {by_id[i]["status"] for i in ("council--gemini", "council--claude", "consensus", "finalize")} == {"pending"}
    assert "reused_from" not in by_id["council--gemini"]
    assert set(materialized) == {sp.name for sp in PIPELINE.specs}


@pytest.mark.parametrize("problem", ["no source", "source failed", "no issues"])
def test_a_council_rerun_needs_a_finished_source_with_issues(problem: str):
    store = Store()
    if problem != "no source":
        store.case["report_run_id"] = R2
        store.runs[R2] = {"status": "failed" if problem == "source failed" else "succeeded", "doc_ids": []}
        store.add_step(R2, "issues", status="failed" if problem == "no issues" else "succeeded")
    with pytest.raises(PermanentStepError) as err:
        asyncio.run(orchestrator(store)._council_rerun_steps(CASE, None, ["gemini"]))
    assert err.value.user_message


def test_a_failed_rerun_keeps_the_published_report_readable():
    store = Store()
    store.case.update(latest_run_id=R3, report_run_id=R2, status="ai")
    steps = [{"spec": "finalize", "critical": True, "status": "failed", "user_error": "The report could not be assembled"}]
    asyncio.run(orchestrator(store)._sync_case(CASE, R3, steps, "failed"))
    assert store.case["status"] == "ready" and "did not finish" in store.case["note"]
    store.case.pop("report_run_id")
    asyncio.run(orchestrator(store)._sync_case(CASE, R3, steps, "failed"))  # nothing published yet: action needed
    assert store.case["status"] == "action"


# ====================================================================== API
class FakeOrchestrator:
    dag = PIPELINE

    def __init__(self, store: Store, members: tuple[str, ...]):
        self.store, self.members = store, list(members)
        self.runs: list[dict[str, Any]] = []
        self.asks: list[dict[str, Any]] = []
        self.resumed: list[str] = []
        self.fail: Exception | None = None

    def council_ids(self) -> list[str]:
        return list(self.members)

    async def start_run(self, case_id: str, *, trigger: str, idem_key: str | None = None, mode: str = "full",
                        source_run_id: str | None = None) -> str:
        if self.fail:
            raise self.fail
        self.runs.append({"trigger": trigger, "idem_key": idem_key, "mode": mode, "source_run_id": source_run_id})
        return R3

    async def start_ask(self, case_id: str, **kw: Any) -> str:
        self.asks.append(kw)
        ask_id = f"q{len(self.asks):012x}"
        self.store.runs[ask_id] = {
            "status": "running", "question": kw["question"], "mode": kw["mode"], "scope": kw["scope"],
            "council_models": kw["members"], "source_run_id": kw["source_run_id"], "source_version": kw["source_version"],
            "created_at": T0, "updated_at": datetime.now(UTC),
        }
        for mid in kw["members"]:
            self.store.add_step(ask_id, "answer", mid, status="pending")
        return ask_id

    async def retry_failed(self, case_id: str, run_id: str) -> int:
        self.resumed.append(run_id)
        return 1

    async def reconcile(self, case_id: str, run_id: str, force: bool = False) -> int:
        return 0


class FakeCouncilStatus:
    """The availability side of the council, as used by ``GET /council/models``."""

    PROBED = {
        "gemini": {"status": "ready", "activeModel": "gemini-1", "detail": "", "checkedAt": T0},
        "claude": {"status": "unavailable", "activeModel": None, "detail": "claude-1: not enabled for this project", "checkedAt": T0},
        "grok": {"status": "fallback", "activeModel": "grok-2", "detail": "grok-1: not enabled; using grok-2", "checkedAt": T0},
    }

    def __init__(self) -> None:
        self.members = {
            mid: SimpleNamespace(id=mid, name=name, vendor=vendor, host="Google Cloud · Agent Platform (global)", mono=mono,
                                 color="#112233", models=[f"{mid}-1", f"{mid}-2"], console_url="https://console.example/{project}/" + mid)
            for mid, name, vendor, mono in (("gemini", "Gemini", "Google", "Ge"), ("claude", "Claude", "Anthropic", "C"),
                                            ("grok", "Grok", "xAI", "Gr"))
        }
        self.state = {mid: {"status": "unknown", "activeModel": None, "detail": "Not checked yet", "checkedAt": None} for mid in self.members}
        self.state["gemini"] = dict(self.PROBED["gemini"])
        self.probed: list[tuple[str, bool]] = []

    def ids(self) -> list[str]:
        return list(self.members)

    def member(self, mid: str) -> Any:
        return self.members[mid]

    def status(self, mid: str) -> dict[str, Any]:
        return self.state[mid]

    def console_url(self, m: Any) -> str:
        return m.console_url.replace("{project}", "test-project")

    def chair_order(self, prefer: Any = ()) -> list[str]:
        return list(self.members)

    async def probe(self, mid: str, *, force: bool = False) -> dict[str, Any]:
        self.probed.append((mid, force))
        self.state[mid] = dict(self.PROBED[mid])
        return self.state[mid]


def make_api(members: tuple[str, ...] = ("gemini", "claude", "grok")) -> tuple[TestClient, Store, FakeOrchestrator, FakeCouncilStatus]:
    routes._outputs_cache.clear()
    store = Store()
    orch, council = FakeOrchestrator(store, members), FakeCouncilStatus()
    settings = SimpleNamespace(stale_run_seconds=600, upload_url_ttl_s=900, ask_max_running_per_case=3)
    app = FastAPI()
    app.include_router(routes.router)
    app.state.container = SimpleNamespace(settings=settings, repo=store, gcs=store, orchestrator=orch, council=council)
    return TestClient(app, raise_server_exceptions=False), store, orch, council


def seed_versions(store: Store) -> None:
    """v1: a legacy full run (its report predates versioning); v2: published, with a council; v3: a council re-run in progress."""
    store.runs[R1] = {"status": "succeeded", "trigger": "upload", "created_at": T0, "finished_at": T0 + timedelta(hours=1),
                      "doc_ids": ["d1", "d2"], "stage": "done", "pct": 100}
    store.legacy["background"] = (R1, {"paragraphs": []})
    store.runs[R2] = {"status": "partial", "trigger": "manual", "mode": "full", "created_at": T0 + timedelta(days=1),
                      "finished_at": T0 + timedelta(days=1, hours=1), "report_ready_at": T0 + timedelta(days=1, hours=1),
                      "doc_count": 3, "counts": {"facts": 40, "issues": 5, "decisions": 7}, "council_models": ["gemini", "claude"],
                      "council": [{"id": "gemini", "status": "succeeded", "model": "gemini-1", "error": None},
                                  {"id": "claude", "status": "unavailable", "model": None, "error": NOT_ENABLED}]}
    store.runs[R3] = {"status": "running", "trigger": "council", "mode": "council", "source_run_id": R2,
                      "created_at": T0 + timedelta(days=2), "council_models": ["gemini", "claude"], "doc_ids": ["d1", "d2", "d3"],
                      "stage": "ai", "pct": 60}
    store.add_step(R3, "council", "gemini", status="running")
    store.add_step(R3, "council", "claude", output=unavailable("claude"), outcome="unavailable")
    store.case.update(latest_run_id=R3, report_run_id=R2, status="ai")


def test_versions_are_listed_newest_first_with_the_published_one_and_their_sources():
    api, store, _, _ = make_api()
    seed_versions(store)
    r = api.get(f"/api/v1/cases/{CASE}/runs")
    assert r.status_code == 200, r.text
    v3, v2, v1 = r.json()
    assert [v3["version"], v2["version"], v1["version"]] == [3, 2, 1]
    assert v3["mode"] == "council" and v3["sourceRunId"] == R2 and v3["sourceVersion"] == 2
    assert v3["hasReport"] is False and v3["published"] is False and v3["status"] == "running"
    assert v3["council"] == [
        {"id": "gemini", "status": "running", "model": None, "error": None},
        {"id": "claude", "status": "unavailable", "model": None, "error": NOT_ENABLED},
    ]
    assert v2["published"] is True and v2["hasReport"] is True and v2["docCount"] == 3
    assert v2["counts"] == {"facts": 40, "issues": 5, "decisions": 7} and v2["council"][1]["status"] == "unavailable"
    assert v1["hasReport"] is True and v1["published"] is False and v1["council"] == [] and v1["docCount"] == 2


def test_a_council_rerun_passes_its_mode_and_double_clicks_collapse_into_one(monkeypatch: pytest.MonkeyPatch):
    api, store, orch, _ = make_api()
    seed_versions(store)
    url = f"/api/v1/cases/{CASE}/runs"
    assert api.post(url, json={"mode": "council"}).status_code == 409  # v3 is still running
    store.runs[R3]["status"] = "succeeded"
    monkeypatch.setattr(routes, "now", lambda: T0)
    for _ in range(2):
        r = api.post(url, json={"mode": "council"})
        assert r.status_code == 202, r.text
    assert r.json()["mode"] == "council" and r.json()["sourceRunId"] == R2
    assert api.post(url).status_code == 202  # no body: a full re-analysis
    assert api.post(url, json={"mode": "council", "sourceRunId": R1}).status_code == 202
    first, again, full, older = orch.runs
    assert first == {"trigger": "manual", "idem_key": first["idem_key"], "mode": "council", "source_run_id": None}
    assert again["idem_key"] == first["idem_key"]  # the engine collapses the same key into one run
    assert full["mode"] == "full" and full["idem_key"] != first["idem_key"]
    assert older["source_run_id"] == R1
    orch.fail = PermanentStepError("no source", "There is no finished analysis to re-run the council on.")
    r = api.post(url, json={"mode": "council"})
    assert r.status_code == 409 and "no finished analysis" in r.json()["detail"]
    assert api.post(url, json={"mode": "council", "sourceRunId": "r1"}).status_code == 422


def test_a_council_rerun_needs_a_configured_council():
    api, store, _, _ = make_api(members=())
    seed_versions(store)
    store.runs[R3]["status"] = "succeeded"
    r = api.post(f"/api/v1/cases/{CASE}/runs", json={"mode": "council"})
    assert r.status_code == 409 and "not configured" in r.json()["detail"]


def test_only_the_latest_version_can_be_resumed():
    api, store, orch, _ = make_api()
    seed_versions(store)
    store.runs[R2]["status"] = store.runs[R3]["status"] = "failed"
    assert api.post(f"/api/v1/cases/{CASE}/runs/{R2}/resume").status_code == 409
    assert api.post(f"/api/v1/cases/{CASE}/runs/{R3}/resume").status_code == 200
    assert orch.resumed == [R3]


def test_a_run_view_marks_unavailable_and_reused_steps():
    api, store, _, _ = make_api()
    seed_versions(store)
    store.add_step(R3, "issues", reused_from=R2)
    r = api.get(f"/api/v1/cases/{CASE}/runs/{R3}")
    assert r.status_code == 200, r.text
    steps = {s["id"]: s for s in r.json()["steps"]}
    assert steps["council--claude"]["outcome"] == "unavailable" and steps["council--claude"]["error"] == NOT_ENABLED
    assert steps["issues"]["reused"] is True and steps["council--gemini"]["reused"] is False
    assert list(steps)[0] == "issues"  # pipeline order
    assert api.get(f"/api/v1/cases/{CASE}/runs/r999999999999").status_code == 404


def test_report_sections_are_served_per_version():
    api, store, _, _ = make_api()
    seed_versions(store)
    store.reports[(R2, "council")] = {"rows": []}
    base = f"/api/v1/cases/{CASE}/report"
    assert api.get(f"{base}/council?run={R2}").json()["runId"] == R2
    assert api.get(f"{base}/council").json()["runId"] == R2  # default: the published version
    assert api.get(f"{base}/council?run={R1}").status_code == 404  # made before the council existed
    assert api.get(f"{base}/background?run={R1}").json()["runId"] == R1  # legacy, unversioned report
    assert api.get(f"{base}/bogus").status_code == 404
    assert api.get(f"{base}/council?run=r123").status_code == 422


def test_asking_needs_a_finished_version_and_valid_input():
    api, store, orch, _ = make_api()
    url = f"/api/v1/cases/{CASE}/asks"
    q = {"question": "Was notice given in time?", "mode": "independent", "scope": {"kind": "record"}}
    assert api.post(url, json=q).status_code == 409  # nothing to ground the question on yet
    seed_versions(store)
    store.reports[(R2, "issues")] = {"issues": [{"n": 1, "topic": "Formation"}, {"n": 2, "topic": "Notice"}]}
    assert api.post(url, json=q | {"members": ["gpt"]}).status_code == 422
    assert api.post(url, json=q | {"mode": "debate", "members": ["claude"]}).status_code == 422
    assert api.post(url, json=q | {"scope": {"kind": "issue", "issue": 9}}).status_code == 422
    assert api.post(url, json=q | {"question": "\x00\x01\x02\x03\x04  ab"}).status_code == 422
    assert api.post(url, json=q | {"runId": R3}).status_code == 409  # v3 has not finished
    r = api.post(url, json=q | {"mode": "debate", "scope": {"kind": "issue", "issue": 2}})
    assert r.status_code == 202, r.text
    started = orch.asks[-1]
    assert started["members"] == ["gemini", "claude", "grok"] and started["source_run_id"] == R2 and started["source_version"] == 2
    assert started["scope"] == {"kind": "issue", "issue": 2, "label": "Issue 2 · Notice"}
    view = r.json()
    assert view["status"] == "running" and view["version"] == 2 and view["scope"]["label"] == "Issue 2 · Notice"
    assert [a["status"] for a in view["answers"]] == ["pending"] * 3 and len(view["reviews"]) == 3
    for _ in range(2):
        assert api.post(url, json=q).status_code == 202
    assert api.post(url, json=q).status_code == 429  # three questions are already running


def seed_ask(store: Store, qid: str, status: str, mode: str) -> None:
    store.runs[qid] = {
        "status": status, "mode": mode, "question": "Was notice given?", "council_models": ["gemini", "claude", "grok"],
        "scope": {"kind": "record", "issue": None, "label": "Whole record"}, "source_run_id": R2, "source_version": 2,
        "created_at": T0, "updated_at": datetime.now(UTC),
    }


def test_the_ask_view_shows_each_member_as_its_answer_arrives():
    api, store, _, _ = make_api()
    seed_versions(store)
    qid = "q0000000000aa"
    seed_ask(store, qid, "running", "debate")
    cite = {"kind": "record", "text": "Contract, p. 12", "status": "verified", "note": "Notice shall be given within 14 days."}
    store.add_step(qid, "answer", "gemini", output={
        "member": "gemini", "status": "succeeded", "model": "gemini-1", "paragraphs": ["Yes, on 14 March."],
        "turnsOnDisputedFact": True, "cites": [cite], "claimant": [], "defendant": [],
    })
    store.add_step(qid, "answer", "claude", status="retrying", user_error="Claude Opus 5.5 is temporarily unavailable — retrying")
    store.add_step(qid, "answer", "grok", output={"member": "grok", "status": "unavailable", "detail": NOT_ENABLED}, outcome="unavailable")
    for mid in ("gemini", "claude", "grok"):
        store.add_step(qid, "review", mid, status="pending")
    store.add_step(qid, "synth", status="pending")
    r = api.get(f"/api/v1/cases/{CASE}/asks/{qid}")
    assert r.status_code == 200, r.text
    v = r.json()
    assert [(a["member"], a["status"]) for a in v["answers"]] == [("gemini", "succeeded"), ("claude", "retrying"), ("grok", "unavailable")]
    gemini, claude, grok = v["answers"]
    assert gemini["paragraphs"] == ["Yes, on 14 March."] and gemini["turnsOnDisputedFact"] is True and gemini["cites"] == [cite]
    assert claude["error"].endswith("retrying") and grok["error"] == NOT_ENABLED
    assert [rv["status"] for rv in v["reviews"]] == ["pending"] * 3
    assert v["synthesis"]["status"] == "pending" and v["steelman"] is None and v["status"] == "running"
    assert api.get(f"/api/v1/cases/{CASE}/asks/q0000000000bb").status_code == 404


def test_a_finished_steelman_returns_the_merged_points():
    api, store, _, _ = make_api()
    qid = "q0000000000cc"
    seed_ask(store, qid, "succeeded", "steelman")
    point = {"point": "Notice was given on 14 March.", "cites": [], "by": ["gemini", "claude"]}
    for mid in ("gemini", "claude"):
        store.add_step(qid, "answer", mid, output={"member": mid, "status": "succeeded", "model": f"{mid}-1", "paragraphs": [],
                                                   "cites": [], "claimant": [point], "defendant": []})
    store.add_step(qid, "answer", "grok", status="failed", user_error="Grok could not answer")
    store.add_step(qid, "synth", output={"status": "succeeded", "chair": "gemini", "model": "gemini-1", "summary": "", "agree": [],
                                         "differ": [], "leftOut": [], "steelman": {"claimant": [point], "defendant": []}})
    v = api.get(f"/api/v1/cases/{CASE}/asks/{qid}").json()
    assert v["status"] == "succeeded" and v["reviews"] == []
    assert v["steelman"] == {"claimant": [point], "defendant": []} and v["synthesis"]["chair"] == "gemini"
    assert v["answers"][2]["status"] == "failed" and v["answers"][2]["error"] == "Grok could not answer"


def test_a_question_nobody_could_answer_is_shown_as_failed():
    api, store, _, _ = make_api()
    qid = "q0000000000dd"
    seed_ask(store, qid, "succeeded", "independent")
    store.runs[qid]["answered"] = []
    for mid in ("gemini", "claude", "grok"):
        store.add_step(qid, "answer", mid, output={"member": mid, "status": "unavailable", "detail": NOT_ENABLED}, outcome="unavailable")
    store.add_step(qid, "synth", output={"status": "skipped"}, outcome="skipped")
    v = api.get(f"/api/v1/cases/{CASE}/asks/{qid}").json()
    assert v["status"] == "failed" and v["synthesis"]["status"] == "skipped"
    listed = api.get(f"/api/v1/cases/{CASE}/asks").json()
    assert [(a["id"], a["status"], a["version"]) for a in listed] == [(qid, "failed", 2)]


def test_council_models_report_availability_with_a_link_to_enable_each_model():
    api, _, _, council = make_api()
    r = api.get("/api/v1/council/models")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chair"] == ["gemini", "claude", "grok"]
    got = {m["id"]: m for m in body["members"]}
    assert (got["gemini"]["status"], got["gemini"]["activeModel"]) == ("ready", "gemini-1")
    assert got["claude"]["status"] == "unavailable" and got["claude"]["consoleUrl"] == "https://console.example/test-project/claude"
    assert got["grok"]["status"] == "fallback" and got["grok"]["m"] == "Gr" and got["grok"]["models"] == ["grok-1", "grok-2"]
    assert sorted(council.probed) == [("claude", False), ("grok", False)]  # only members not checked yet are probed
    api.get("/api/v1/council/models?refresh=1")
    assert sorted(p for p in council.probed if p[1]) == [("claude", True), ("gemini", True), ("grok", True)]
