"""Pure unit tests: DAG readiness, fan-out, skip cascade, outcomes."""

from __future__ import annotations

from app.harness.dag import ASK, COUNCIL_REDO, PIPELINE, TERMINAL

MEMBERS = ("gemini", "claude")


def _state(doc_ids=("d1", "d2"), models=MEMBERS):
    steps, mat = PIPELINE.initial_steps(doc_ids, models)
    return {s["id"]: s for s in steps}, set(mat)


def _set(steps, sid, status, **kw):
    steps[sid].update(status=status, **kw)


def _ready(steps, mat):
    return PIPELINE.evaluate(list(steps.values()), mat)


def test_initial_only_ingest_ready():
    steps, mat = _state()
    ready, skipped = _ready(steps, mat)
    assert sorted(ready) == ["ingest--d1", "ingest--d2"]
    assert skipped == []
    assert "mapping" not in mat and "grounding" not in mat


def test_facts_per_document_start_as_soon_as_own_ingest_finishes():
    steps, mat = _state()
    _set(steps, "ingest--d1", "succeeded")
    _set(steps, "ingest--d2", "running")
    ready, _ = _ready(steps, mat)
    assert ready == ["facts--d1"]  # background waits for all ingests


def test_background_and_facts_run_in_parallel():
    steps, mat = _state()
    for d in ("d1", "d2"):
        _set(steps, f"ingest--{d}", "succeeded")
    ready, _ = _ready(steps, mat)
    assert set(ready) == {"background", "facts--d1", "facts--d2"}


def test_failed_ingest_skips_only_its_facts():
    steps, mat = _state()
    _set(steps, "ingest--d1", "succeeded")
    _set(steps, "ingest--d2", "failed")
    ready, skipped = _ready(steps, mat)
    assert skipped == ["facts--d2"]
    assert set(ready) == {"background", "facts--d1"}  # ingest is optional: degraded run continues


def _through_issues(steps, mat, keys=("1", "2")):
    for sid, st in list(steps.items()):
        if st["spec"] in ("ingest", "facts", "background", "chronology"):
            _set(steps, sid, "succeeded")
    _set(steps, "issues", "succeeded", fanout=list(keys))
    for st in PIPELINE.expand(list(steps.values()), mat):
        steps[st["id"]] = st


def test_issues_fan_out_mapping_and_grounding_in_parallel():
    steps, mat = _state()
    _through_issues(steps, mat)
    assert {"mapping", "grounding"} <= mat
    ready, _ = _ready(steps, mat)
    assert set(ready) == {"mapping--1", "mapping--2", "grounding--1", "grounding--2"}


def test_verify_waits_for_all_mapping_and_finalize_for_everything():
    steps, mat = _state()
    _through_issues(steps, mat)
    _set(steps, "mapping--1", "succeeded")
    _set(steps, "mapping--2", "running")
    ready, _ = _ready(steps, mat)
    assert "verify" not in ready
    _set(steps, "mapping--2", "failed")  # optional failure -> verify still runs
    ready, _ = _ready(steps, mat)
    assert "verify" in ready and "finalize" not in ready


def test_critical_failure_cascades_and_fails_run():
    steps, mat = _state()
    for sid, st in steps.items():
        if st["spec"] in ("ingest", "facts", "background"):
            _set(steps, sid, "succeeded")
    _set(steps, "chronology", "failed")
    _, skipped = _ready(steps, mat)
    assert "issues" in skipped
    for sid in skipped:
        _set(steps, sid, "skipped")
    for st in PIPELINE.expand(list(steps.values()), mat):  # issues skipped -> zero fan-out instances
        steps[st["id"]] = st
    _, skipped = _ready(steps, mat)
    for sid in skipped:
        _set(steps, sid, "skipped")
    assert all(s["status"] in TERMINAL for s in steps.values())
    assert PIPELINE.outcome(list(steps.values()), mat) == "failed"


def test_partial_when_optional_step_fails():
    steps, mat = _state()
    _through_issues(steps, mat, keys=("1",))
    for sid in ("mapping--1", "verify", "council--gemini", "council--claude", "consensus", "finalize"):
        _set(steps, sid, "succeeded")
    _set(steps, "grounding--1", "failed")
    assert PIPELINE.outcome(list(steps.values()), mat) == "partial"


def test_outcome_none_until_fanouts_materialised():
    steps, mat = _state()
    for sid in steps:
        _set(steps, sid, "succeeded")
    assert PIPELINE.outcome(list(steps.values()), mat) is None


def test_council_is_one_step_per_member_and_waits_for_verified_law():
    steps, mat = _state()
    assert {"council--gemini", "council--claude"} <= set(steps) and "council" in mat
    _through_issues(steps, mat, keys=("1",))
    _set(steps, "mapping--1", "succeeded")
    _set(steps, "grounding--1", "succeeded")
    ready, _ = _ready(steps, mat)
    assert "verify" in ready and not any(r.startswith("council") for r in ready)
    _set(steps, "verify", "succeeded")
    ready, _ = _ready(steps, mat)
    assert set(ready) == {"council--gemini", "council--claude"}
    _set(steps, "council--gemini", "succeeded")
    _set(steps, "council--claude", "failed")  # optional: a failed member degrades, never blocks
    ready, _ = _ready(steps, mat)
    assert ready == ["consensus"]
    _set(steps, "consensus", "succeeded")
    ready, _ = _ready(steps, mat)
    assert ready == ["finalize"]


def test_no_council_members_still_finishes():
    steps, mat = _state(models=())
    _through_issues(steps, mat, keys=("1",))
    for sid in ("mapping--1", "grounding--1", "verify"):
        _set(steps, sid, "succeeded")
    ready, _ = _ready(steps, mat)
    assert "consensus" in ready  # zero council instances: consensus no-ops, finalize follows


def test_ask_dag_answers_then_reviews_then_synthesis():
    steps, mat = ASK.initial_steps([], MEMBERS)
    steps = {s["id"]: s for s in steps}
    mat = set(mat)
    assert ASK.name == "ask" and set(steps) == {"answer--gemini", "answer--claude", "review--gemini", "review--claude", "synth"}
    ready, _ = ASK.evaluate(list(steps.values()), mat)
    assert set(ready) == {"answer--gemini", "answer--claude"}
    _set(steps, "answer--gemini", "succeeded")
    _set(steps, "answer--claude", "running")
    ready, _ = ASK.evaluate(list(steps.values()), mat)
    assert ready == []  # reviews wait for every answer
    _set(steps, "answer--claude", "failed")
    ready, _ = ASK.evaluate(list(steps.values()), mat)
    assert set(ready) == {"review--gemini", "review--claude"}
    for sid in ("review--gemini", "review--claude", "synth"):
        _set(steps, sid, "succeeded")
    assert ASK.outcome(list(steps.values()), mat) == "partial"


def test_council_redo_specs_exist():
    assert set(COUNCIL_REDO) <= set(PIPELINE.by_name)
    assert PIPELINE.specs[-1].name == "finalize" and "finalize" in COUNCIL_REDO
