"""Model council pre-analysis.

``council--<member>`` (one step per member, in parallel): each model independently reads the
record, the chronology, the issues and the verified authorities, and returns its reading of every
issue, the facts most likely to decide the case and questions for counsel. Citations are checked
deterministically afterwards.

``consensus``: the chair model groups the readings of each issue into at most two positions and
merges the flagged facts and questions. It only compares; it adds no analysis. If it cannot run,
the report still shows every member's own readings (``compared = false``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.agents.base import AgentContext, AgentResult
from app.agents.record import (
    INJECTION_GUARD,
    check_cite,
    check_cites,
    corpus_block,
    load_record,
    member_corpus_budget,
    render_brief,
)
from app.agents.schemas import ConsensusDraft, CouncilReadingOutput
from app.harness.resilience import NOT_ENABLED_DETAIL, PermanentStepError, RetryableStepError, SchemaError, UnavailableError
from app.logging_setup import get_logger

log = get_logger(__name__)

COUNCIL_SYSTEM = f"""You are one member of a council of independent AI models assisting a judge of the DIFC Courts.
You read the case record and the legal issues identified by the analysis, and give your own neutral reading of each issue.
You do not decide the case, predict the outcome or favour either party.

Rules:
- Ground every statement in the case record or in the VERIFIED AUTHORITIES listed for that issue. Never invent facts,
  documents, page references or authorities. Never cite an authority that is not in the verified list for the issue;
  the Google Search notes are context only.
- Cite record passages by copying a tag's content exactly (e.g. 'Contract, p. 12') and authorities as 'Name [citation]'
  exactly as listed.
- For each issue: 'reading' = one or two neutral sentences on how the issue is structured and what it turns on
  (e.g. "Clause 20.1 operates as a condition precedent; the issue is whether the 14 March letter was notice under it");
  'turns_on' = the single decisive point (a fact, date, document or legal test); 'confidence' = how clearly the record
  answers the issue (high, medium or low); 'cites' = one to four citations.
- 'flagged': the two to five facts or gaps in the record most likely to decide the case, each with a record citation.
- 'questions': three to eight short, neutral questions the judge could put to counsel to resolve what the record leaves
  open, each tied to an issue number and, where possible, to a record citation.
- Plain British English. Be concise.
- {INJECTION_GUARD}"""

CONSENSUS_SYSTEM = f"""You compare the readings that several independent AI models gave of the same legal issues in a
DIFC Courts case. You add no analysis of your own and you decide nothing.

For each issue:
- Group the members' readings into positions. If the readings agree in substance (even if worded differently), return
  ONE position. If they genuinely differ on how the issue is structured or what it turns on, return the TWO main
  competing positions.
- Write each position as one or two neutral sentences using only what the members said. Do not name the members in it.
- In 'members', list the ids of the members holding that position. Every member that gave a reading of the issue must
  appear in exactly one position.
Then merge the members' flagged facts and their questions for counsel: combine items with the same substance, keep the
clearest wording and a record citation, and list every member who raised each one. At most 8 flagged facts and 10
questions, the most widely shared first.
Use the member ids exactly as given.
- {INJECTION_GUARD}"""


def _unavailable(member: Any, exc: UnavailableError) -> AgentResult:
    detail = getattr(exc, "detail", None) or NOT_ENABLED_DETAIL
    log.warning("council member %s unavailable: %s", member.id, str(exc)[:300])
    return AgentResult(
        output={"member": member.id, "name": member.name, "status": "unavailable", "model": None, "detail": detail,
                "readings": [], "flagged": [], "questions": []},
        outcome="unavailable",
    )


class CouncilMemberAgent:
    name = "council"

    async def run(self, ctx: AgentContext) -> AgentResult:
        if ctx.council is None or not ctx.key:
            raise PermanentStepError("council step without a council", "The model council is not configured")
        m = ctx.council.member(ctx.key)
        view = await load_record(ctx, ctx.run_id)
        valid = {int(i["n"]) for i in view.issues}
        if not valid:
            return AgentResult(output={"member": m.id, "name": m.name, "status": "succeeded", "model": None,
                                       "readings": [], "flagged": [], "questions": []})
        corpus = corpus_block(view, member_corpus_budget(m.max_input_chars))
        task = (
            "\n\nTASK: Give your reading of every issue listed above (Issues "
            + ", ".join(str(n) for n in sorted(valid))
            + "), then the flagged facts and your questions for counsel."
        )
        try:
            res = await ctx.council.generate(
                m.id, schema=CouncilReadingOutput, system=COUNCIL_SYSTEM,
                contents=[corpus, render_brief(view) + task], temperature=0.2,
            )
        except UnavailableError as exc:
            return _unavailable(m, exc)
        ctx.track(res)

        readings: list[dict[str, Any]] = []
        seen: set[int] = set()
        for r in res.data.readings:
            if r.issue not in valid or r.issue in seen or not r.reading.strip():
                continue
            seen.add(r.issue)
            readings.append({
                "issue": r.issue, "reading": r.reading.strip(), "turns_on": r.turns_on.strip(),
                "confidence": r.confidence, "cites": check_cites(r.cites, view, limit=6),
            })
        if not readings:
            raise SchemaError(f"{m.id} returned no reading for any known issue", f"{m.name} returned no usable reading")
        readings.sort(key=lambda r: r["issue"])
        flagged = [
            {"text": f.text.strip(), "ref": f.ref.strip(), "check": check_cite("record", f.ref, view)["status"] if f.ref.strip() else "warn"}
            for f in res.data.flagged[:8] if f.text.strip()
        ]
        questions = [
            {"to": q.to, "question": q.question.strip(), "why": q.why.strip(),
             "issue": q.issue if q.issue in valid else 0, "ref": q.ref.strip()}
            for q in res.data.questions[:10] if q.question.strip()
        ]
        return AgentResult(output={
            "member": m.id, "name": m.name, "status": "succeeded", "model": res.model,
            "readings": readings, "flagged": flagged, "questions": questions,
        })


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _merge_items(per_member: dict[str, list[dict[str, Any]]], key: str, limit: int) -> list[dict[str, Any]]:
    """Deterministic merge (exact duplicates only), used when no chair is needed or available."""
    merged: dict[str, dict[str, Any]] = {}
    for mid, items in per_member.items():
        for it in items:
            k = _norm(it.get(key, ""))
            if not k:
                continue
            if k in merged:
                if mid not in merged[k]["members"]:
                    merged[k]["members"].append(mid)
            else:
                merged[k] = {**it, "members": [mid]}
    out = sorted(merged.values(), key=lambda x: -len(x["members"]))
    return out[:limit]


class ConsensusAgent:
    name = "consensus"

    async def run(self, ctx: AgentContext) -> AgentResult:
        outs = await ctx.outputs("council")
        ok = {k: v for k, v in outs.items() if v.get("status") == "succeeded" and v.get("readings")}
        if not ok:
            return AgentResult(output={"compared": False, "chair": None, "issues": [], "flagged": [], "questions": []},
                               outcome="skipped")
        flagged_by = {mid: o.get("flagged", []) for mid, o in ok.items()}
        questions_by = {mid: o.get("questions", []) for mid, o in ok.items()}
        if len(ok) == 1:  # one reading: nothing to compare, no model call
            mid, o = next(iter(ok.items()))
            return AgentResult(output={
                "compared": True, "chair": None,
                "issues": [{"issue": r["issue"], "positions": [{"text": r["reading"], "members": [mid]}]} for r in o["readings"]],
                "flagged": _merge_items(flagged_by, "text", 8), "questions": _merge_items(questions_by, "question", 10),
            })
        if ctx.council is None:
            raise PermanentStepError("consensus without a council", "The model council is not configured")

        issues = ((await ctx.output("issues")) or {}).get("issues", [])
        topics = {int(i["n"]): i.get("topic", "") for i in issues}
        holders: dict[int, list[str]] = {}
        lines = [f"MEMBER IDS: {', '.join(ok)}\n\nREADINGS BY ISSUE\n"]
        for n in sorted({r["issue"] for o in ok.values() for r in o["readings"]}):
            lines.append(f"\nIssue {n} · {topics.get(n, '')}\n")
            for mid, o in ok.items():
                r = next((x for x in o["readings"] if x["issue"] == n), None)
                if r:
                    holders.setdefault(n, []).append(mid)
                    lines.append(f"- {mid}: {r['reading']} | Turns on: {r['turns_on']} | Confidence: {r['confidence']}\n")
        lines.append("\nFLAGGED FACTS BY MEMBER\n")
        for mid, items in flagged_by.items():
            lines += [f"- {mid}: {f['text']} ({f['ref']})\n" for f in items]
        lines.append("\nQUESTIONS FOR COUNSEL BY MEMBER\n")
        for mid, items in questions_by.items():
            lines += [f"- {mid}: [to {q['to']}, Issue {q['issue']}] {q['question']} Why: {q['why']} ({q['ref']})\n" for q in items]
        payload = "".join(lines)

        res, chair, errors = None, None, []
        for chair_id in ctx.council.chair_order(prefer=ok):
            try:
                res = await ctx.council.generate(
                    chair_id, schema=ConsensusDraft, system=CONSENSUS_SYSTEM, contents=[payload],
                    temperature=0.0, max_output_tokens=16_000,
                )
                chair = chair_id
                break
            except Exception as exc:  # noqa: BLE001 - try the next chair; the step retries if none answers
                errors.append(f"{chair_id}: {str(exc)[:200]}")
                log.warning("consensus: chair %s failed: %s", chair_id, str(exc)[:300])
        if res is None or chair is None:
            raise RetryableStepError("no chair could compare the readings: " + "; ".join(errors), "The council's readings could not be compared yet")
        ctx.track(res)

        out_issues: list[dict[str, Any]] = []
        done: set[int] = set()
        for d in res.data.issues:
            if d.issue not in holders or d.issue in done:
                continue
            done.add(d.issue)
            assigned: set[str] = set()
            positions = []
            for p in d.positions:
                ms = [mid for mid in dict.fromkeys(p.members) if mid in holders[d.issue] and mid not in assigned]
                if ms and p.text.strip():
                    assigned |= set(ms)
                    positions.append({"text": p.text.strip(), "members": ms})
            positions.sort(key=lambda p: -len(p["members"]))  # stable: the majority reading is A
            out_issues.append({"issue": d.issue, "positions": positions[:2]})

        def members_of(item: Any) -> list[str]:
            return [mid for mid in dict.fromkeys(item.members) if mid in ok]

        flagged = [
            {"text": f.text.strip(), "ref": f.ref.strip(), "members": members_of(f)}
            for f in res.data.flagged if f.text.strip() and members_of(f)
        ]
        questions = [
            {"to": q.to, "question": q.question.strip(), "why": q.why.strip(),
             "issue": q.issue if q.issue in topics else 0, "ref": q.ref.strip(), "members": members_of(q)}
            for q in res.data.questions if q.question.strip() and members_of(q)
        ]
        flagged.sort(key=lambda x: -len(x["members"]))
        questions.sort(key=lambda x: -len(x["members"]))
        return AgentResult(output={
            "compared": True, "chair": {"id": chair, "model": res.model}, "issues": out_issues,
            "flagged": flagged[:8] or _merge_items(flagged_by, "text", 8),
            "questions": questions[:10] or _merge_items(questions_by, "question", 10),
        })


# ------------------------------------------------------------------ report sections (used by finalize)
def _iso(ts: Any) -> str | None:
    return ts.astimezone(UTC).isoformat() if isinstance(ts, datetime) else None


async def council_sections(ctx: AgentContext, issues: list[dict[str, Any]], run: dict[str, Any]) -> tuple[dict, dict, list[dict]] | None:
    """Build the ``council`` and ``questions`` report sections and the run's council summary.

    Returns ``None`` when the council was not part of this run (disabled, or a version made
    before the council existed).
    """
    steps = await ctx.step_states("council")
    order = list(run.get("council_models") or []) or [s.get("key") for s in steps if s.get("key")]
    if not order:
        return None
    outs = await ctx.outputs("council")
    cons = await ctx.output("consensus")
    cons_steps = await ctx.step_states("consensus")
    by_key = {s.get("key"): s for s in steps}
    cfg = getattr(ctx.council, "members", {}) if ctx.council is not None else {}

    members: list[dict[str, Any]] = []
    for mid in order:
        o, st, c = outs.get(mid), by_key.get(mid) or {}, cfg.get(mid)
        name = (o or {}).get("name") or (c.name if c else mid)
        if o and o.get("status") == "unavailable":
            status, model, error = "unavailable", None, o.get("detail") or "Not enabled in Model Garden for this project"
        elif o and o.get("status") == "succeeded":
            status, model, error = "succeeded", o.get("model"), None
        else:
            status, model, error = "failed", None, st.get("user_error") or "Did not complete"
        members.append({
            "id": mid, "name": name, "m": c.mono if c else mid[:2].title(), "c": c.color if c else "#6B7280",
            "status": status, "model": model, "error": error,
        })
    ok = [m["id"] for m in members if m["status"] == "succeeded"]
    names = {m["id"]: m["name"] for m in members}

    readings: dict[int, list[dict[str, Any]]] = {}
    for mid in ok:
        for r in (outs.get(mid) or {}).get("readings", []):
            readings.setdefault(int(r["issue"]), []).append({
                "member": mid, "text": r["reading"], "turnsOn": r.get("turns_on", ""),
                "confidence": r.get("confidence", "medium"), "cites": r.get("cites", []),
            })
    compared = bool(cons and cons.get("compared") and len(ok) > 0)
    positions = {int(d["issue"]): d.get("positions", []) for d in (cons or {}).get("issues", [])} if compared else {}

    rows: list[dict[str, Any]] = []
    for iss in issues:
        n = int(iss["n"])
        if n not in readings:
            continue
        pos = positions.get(n, [])[:2]
        votes: dict[str, str] = {}
        if compared:
            votes = {mid: "-" for mid in order}
            for label, p in zip(("A", "B"), pos):
                for mid in p.get("members", []):
                    if mid in votes:
                        votes[mid] = label
        rows.append({
            "n": n, "topic": iss.get("topic", ""),
            "a": pos[0]["text"] if compared and pos else "", "b": pos[1]["text"] if compared and len(pos) > 1 else "",
            "votes": votes, "readings": readings[n],
        })

    if compared:
        flagged_src, questions_src = cons.get("flagged", []), cons.get("questions", [])
    else:
        flagged_src = _merge_items({mid: (outs.get(mid) or {}).get("flagged", []) for mid in ok}, "text", 8)
        questions_src = _merge_items({mid: (outs.get(mid) or {}).get("questions", []) for mid in ok}, "question", 10)
    flagged = [{"t": f["text"], "ref": f.get("ref", ""), "by": list(f.get("members", []))} for f in flagged_src]
    questions = [
        {"id": f"q{i + 1}", "to": q.get("to", "Both"), "q": q["question"], "why": q.get("why", ""),
         "iss": int(q.get("issue") or 0), "ref": q.get("ref", ""), "by": list(q.get("members", []))}
        for i, q in enumerate(questions_src)
    ]

    notes = []
    for m in members:
        if m["status"] == "unavailable":
            notes.append(f"{m['name']} was unavailable: not enabled in Model Garden for this project.")
        elif m["status"] == "failed":
            notes.append(f"{m['name']} did not complete: {m['error']}.")
    if not ok:
        notes.append("No council member produced a reading for this version.")
    elif not compared:
        notes.append("The readings could not be compared automatically; each model's reading is shown separately.")

    times = [s for s in steps + cons_steps if isinstance(s.get("finished_at"), datetime)]
    starts = [s["started_at"] for s in steps if isinstance(s.get("started_at"), datetime)]
    ran_at = max((s["finished_at"] for s in times), default=datetime.now(UTC))
    duration = round((ran_at - min(starts)).total_seconds()) if starts else None
    chair = (cons or {}).get("chair") if compared else None

    council = {
        "ranAt": _iso(ran_at), "durationS": duration, "chair": chair, "compared": compared, "note": " ".join(notes),
        "members": members, "rows": rows, "flagged": flagged,
    }
    summary = [{"id": m["id"], "status": m["status"], "model": m["model"], "error": m["error"]} for m in members]
    log.info("council section: %d/%d members succeeded, compared=%s (%s)", len(ok), len(order), compared, ", ".join(names.get(i, i) for i in ok))
    return council, {"questions": questions}, summary
