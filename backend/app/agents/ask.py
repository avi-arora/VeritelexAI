"""Ask the council: one durable mini-run per question, grounded on a finished report version.

``answer--<member>``  each member answers independently (or, in steel-man mode, builds the
                      strongest case for each side) from the version's record and verified law.
``review--<member>``  debate mode only: each member reads the others' answers (anonymised as
                      "Answer 1..N"), notes weaknesses and revises its own position.
``synth``             the chair says where the answers agree and differ (or merges the steel-man
                      points). Unverified citations ("left out") are computed, not model-judged.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentContext, AgentResult
from app.agents.record import (
    INJECTION_GUARD,
    RecordView,
    check_cites,
    corpus_block,
    load_record,
    member_corpus_budget,
    render_brief,
)
from app.agents.schemas import AskAnswerDraft, ReviewDraft, SteelmanDraft, SteelmanMergeDraft, SynthesisDraft
from app.harness.resilience import NOT_ENABLED_DETAIL, PermanentStepError, RetryableStepError, UnavailableError
from app.logging_setup import get_logger

log = get_logger(__name__)

_RULES = f"""Rules:
- Ground every statement in the case record or in the VERIFIED AUTHORITIES listed for the issues. Never invent facts,
  documents, page references or authorities; the Google Search notes are context only and must not be cited.
- Cite record passages by copying a tag's content exactly (e.g. 'Contract, p. 12') and authorities as 'Name [citation]'
  exactly as listed.
- If the record does not answer the question, say so plainly and say what would answer it.
- You assist the judge; you do not decide the case or predict its outcome. Plain British English, concise.
- {INJECTION_GUARD}"""

ANSWER_SYSTEM = (
    "You are one member of a council of independent AI models assisting a judge of the DIFC Courts. The judge has asked "
    "a question about the case. Answer it in one to four short paragraphs and give the citations that support it. Set "
    "'turns_on_disputed_fact' to true if the answer depends on a fact the parties dispute.\n" + _RULES
)
STEELMAN_SYSTEM = (
    "You are one member of a council of independent AI models assisting a judge of the DIFC Courts. On the judge's "
    "question, set out the strongest case for EACH side: two to five points for the Claimant and two to five for the "
    "Defendant, each one or two sentences with its citations. Be even-handed: argue each side as well as its own "
    "counsel would, using only the record and the verified authorities.\n" + _RULES
)
REVIEW_SYSTEM = (
    "You are one member of a council of independent AI models assisting a judge of the DIFC Courts. You answered the "
    "judge's question; now read the other members' answers (numbered). In 'notes', point out specific weaknesses: factual "
    "errors against the record, omissions, unsupported or misused citations, or reasoning gaps (at most two notes per "
    "answer; refer to an answer only by its number). Then give your revised position in two or three sentences, keeping "
    "what still stands and correcting what does not.\n" + _RULES
)
SYNTH_SYSTEM = (
    "You chair a council of independent AI models assisting a judge of the DIFC Courts. Several members answered the "
    "judge's question (numbered answers below, with their reviews if any). Say neutrally where they land together and "
    "where they differ, attributing each difference to the answers by number (e.g. 'Answer 2 reads clause 20.1 as...'). "
    "Add no analysis of your own and do not choose between them.\n- " + INJECTION_GUARD
)
STEELMAN_MERGE_SYSTEM = (
    "You chair a council of independent AI models assisting a judge of the DIFC Courts. Each member set out the strongest "
    "case for each side. Merge their points into one list per side: combine points with the same substance, keep the "
    "clearest wording, keep their citations exactly as given, and list in 'members' the ids of every member who made the "
    "point. At most six points per side, the most widely made first. Add no new points.\n- " + INJECTION_GUARD
)

_ANSWER_REF = re.compile(r"\b[Aa]nswer\s+(\d{1,2})\b")


def _tokens(text: str, numbered: dict[int, str]) -> str:
    """Replace 'Answer N' with the member-mention token the UI renders (anonymisation-aware)."""
    return _ANSWER_REF.sub(lambda m: f"{{{{m:{numbered[int(m.group(1))]}}}}}" if int(m.group(1)) in numbered else m.group(0), text or "")


async def _ask(ctx: AgentContext) -> dict[str, Any]:
    ask = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
    if not ask or not ask.get("source_run_id"):
        raise PermanentStepError(f"ask {ctx.run_id} has no source version", "This question is not linked to a report version")
    return ask


def _scope_issue(ask: dict[str, Any]) -> int | None:
    scope = ask.get("scope") or {}
    return int(scope["issue"]) if scope.get("kind") == "issue" and scope.get("issue") is not None else None


def _question_block(ask: dict[str, Any], view: RecordView) -> str:
    issue = _scope_issue(ask)
    scope = f"Scope: {view.issue_label(issue)}." if issue is not None else "Scope: the whole record."
    # The question comes from the judge (validated, at most 2,000 characters).
    return f"\n\nTHE JUDGE'S QUESTION ({scope})\n<<<\n{ask.get('question', '').strip()}\n>>>\n"


def _unavailable(member_id: str, exc: Exception) -> AgentResult:
    log.warning("council member %s unavailable for ask: %s", member_id, str(exc)[:300])
    return AgentResult(
        output={"member": member_id, "status": "unavailable", "detail": getattr(exc, "detail", None) or NOT_ENABLED_DETAIL},
        outcome="unavailable",
    )


def _need_council(ctx: AgentContext) -> Any:
    if ctx.council is None or not ctx.key and ctx.step.get("spec") != "synth":
        raise PermanentStepError("ask step without a council", "The model council is not configured")
    return ctx.council


class AnswerAgent:
    name = "answer"

    async def run(self, ctx: AgentContext) -> AgentResult:
        council = _need_council(ctx)
        m = council.member(ctx.key)
        ask = await _ask(ctx)
        view = await load_record(ctx, ask["source_run_id"])
        corpus = corpus_block(view, member_corpus_budget(m.max_input_chars, ctx.settings.ask_corpus_chars))
        steel = ask.get("mode") == "steelman"
        task = render_brief(view, _scope_issue(ask)) + _question_block(ask, view)
        try:
            res = await council.generate(
                m.id, schema=SteelmanDraft if steel else AskAnswerDraft, system=STEELMAN_SYSTEM if steel else ANSWER_SYSTEM,
                contents=[corpus, task], temperature=0.3,
            )
        except UnavailableError as exc:
            return _unavailable(m.id, exc)
        ctx.track(res)
        out: dict[str, Any] = {
            "member": m.id, "status": "succeeded", "model": res.model, "paragraphs": [], "turnsOnDisputedFact": False,
            "cites": [], "claimant": [], "defendant": [],
        }
        if steel:
            for side in ("claimant", "defendant"):
                out[side] = [
                    {"point": p.point.strip(), "cites": check_cites(p.cites, view, limit=4), "by": [m.id]}
                    for p in getattr(res.data, side)[:6] if p.point.strip()
                ]
            if not out["claimant"] and not out["defendant"]:
                raise RetryableStepError(f"{m.id} returned no points", f"{m.name} returned an empty answer")
        else:
            out["paragraphs"] = [p.strip() for p in res.data.paragraphs if p.strip()][:6]
            out["turnsOnDisputedFact"] = bool(res.data.turns_on_disputed_fact)
            out["cites"] = check_cites(res.data.cites, view)
            if not out["paragraphs"]:
                raise RetryableStepError(f"{m.id} returned an empty answer", f"{m.name} returned an empty answer")
        return AgentResult(output=out)


def _answer_text(o: dict[str, Any]) -> str:
    cites = "; ".join(f"{c['text']} [{c['status']}]" for c in o.get("cites", []))
    return "\n".join(o.get("paragraphs", [])) + (f"\nCitations (verification): {cites}" if cites else "")


class ReviewAgent:
    name = "review"

    async def run(self, ctx: AgentContext) -> AgentResult:
        ask = await _ask(ctx)
        skipped = {"member": ctx.key, "status": "skipped", "notes": [], "revised": ""}
        if ask.get("mode") != "debate":
            return AgentResult(output=skipped, outcome="skipped")
        council = _need_council(ctx)
        m = council.member(ctx.key)
        answers = await ctx.outputs("answer")
        mine = answers.get(m.id)
        others = [(mid, o) for mid, o in answers.items() if mid != m.id and o.get("status") == "succeeded"]
        if not mine or mine.get("status") != "succeeded" or not others:
            return AgentResult(output=skipped, outcome="skipped")
        numbered = {i + 1: mid for i, (mid, _) in enumerate(others)}
        view = await load_record(ctx, ask["source_run_id"])
        text = (
            _question_block(ask, view)
            + "\nYOUR ANSWER\n" + _answer_text(mine) + "\n"
            + "".join(f"\nANSWER {i}\n{_answer_text(o)}\n" for i, (_, o) in enumerate(others, start=1))
            + "\nTASK: review the numbered answers, then give your revised position."
        )
        try:
            res = await council.generate(
                m.id, schema=ReviewDraft, system=REVIEW_SYSTEM,
                contents=[render_brief(view, _scope_issue(ask)), text], temperature=0.2, max_output_tokens=8_000,
            )
        except UnavailableError as exc:
            return _unavailable(m.id, exc)
        ctx.track(res)
        notes = [
            {"about": numbered[n.answer], "point": _tokens(n.point.strip(), numbered)}
            for n in res.data.notes if n.answer in numbered and n.point.strip()
        ][: 2 * len(numbered)]
        return AgentResult(output={
            "member": m.id, "status": "succeeded", "model": res.model, "notes": notes,
            "revised": _tokens(res.data.revised.strip(), numbered),
        })


class SynthAgent:
    name = "synth"

    async def run(self, ctx: AgentContext) -> AgentResult:
        ask = await _ask(ctx)
        answers = await ctx.outputs("answer")
        order = list(ask.get("council_models") or answers)
        ok = {mid: answers[mid] for mid in order if (answers.get(mid) or {}).get("status") == "succeeded"}
        # Recorded on the ask so the questions list can tell "no member could answer" from success.
        await ctx.repo.update_run(ctx.case_id, ctx.run_id, {"answered": list(ok)})
        base: dict[str, Any] = {"status": "succeeded", "chair": None, "model": None, "summary": "", "agree": [], "differ": [],
                                "leftOut": _left_out(ok.values()), "steelman": None}
        if not ok:
            return AgentResult(output=base | {"status": "skipped"}, outcome="skipped")
        steel = ask.get("mode") == "steelman"
        if len(ok) == 1:  # one answer: nothing to compare or merge, no model call
            mid, o = next(iter(ok.items()))
            if steel:
                base["steelman"] = {"claimant": o.get("claimant", []), "defendant": o.get("defendant", [])}
            else:
                base["summary"] = f"Only {{{{m:{mid}}}}} answered, so there is nothing to compare."
            return AgentResult(output=base)
        council = _need_council(ctx)
        numbered = {i + 1: mid for i, mid in enumerate(ok)}
        view = await load_record(ctx, ask["source_run_id"])
        if steel:
            lines = [_question_block(ask, view), f"\nMEMBER IDS: {', '.join(ok)}\n"]
            for side in ("claimant", "defendant"):
                lines.append(f"\n{side.upper()} POINTS BY MEMBER\n")
                for mid, o in ok.items():
                    lines += [
                        f"- {mid}: {p['point']} | cites: " + "; ".join(f"{c['kind']}: {c['text']}" for c in p.get("cites", [])) + "\n"
                        for p in o.get(side, [])
                    ]
            schema, system, payload = SteelmanMergeDraft, STEELMAN_MERGE_SYSTEM, "".join(lines)
        else:
            reviews = await ctx.outputs("review") if ask.get("mode") == "debate" else {}
            num_of = {mid: i for i, mid in numbered.items()}
            lines = [_question_block(ask, view)]
            for i, mid in numbered.items():
                lines.append(f"\nANSWER {i}\n{_answer_text(ok[mid])}\n")
                rv = reviews.get(mid) or {}
                if rv.get("status") == "succeeded" and rv.get("revised"):
                    revised = re.sub(r"\{\{m:([a-z0-9]+)\}\}", lambda x: f"Answer {num_of.get(x.group(1), '?')}", rv["revised"])
                    lines.append(f"Revised position of Answer {i} after reading the others: {revised}\n")
            schema, system, payload = SynthesisDraft, SYNTH_SYSTEM, "".join(lines)

        res, chair, errors = None, None, []
        for chair_id in council.chair_order(prefer=ok):
            try:
                res = await council.generate(chair_id, schema=schema, system=system, contents=[payload], temperature=0.0, max_output_tokens=8_000)
                chair = chair_id
                break
            except Exception as exc:  # noqa: BLE001 - try the next chair; the step retries if none answers
                errors.append(f"{chair_id}: {str(exc)[:200]}")
                log.warning("synth: chair %s failed: %s", chair_id, str(exc)[:300])
        if res is None or chair is None:
            raise RetryableStepError("no chair could synthesise: " + "; ".join(errors), "The synthesis could not be written yet")
        ctx.track(res)
        base |= {"chair": chair, "model": res.model}
        if steel:
            def merged(points: list[Any]) -> list[dict[str, Any]]:
                out = []
                for p in points[:6]:
                    by = [mid for mid in dict.fromkeys(p.members) if mid in ok]
                    if p.point.strip() and by:
                        out.append({"point": p.point.strip(), "cites": check_cites(p.cites, view, limit=4), "by": by})
                return sorted(out, key=lambda x: -len(x["by"]))
            base["steelman"] = {"claimant": merged(res.data.claimant), "defendant": merged(res.data.defendant)}
        else:
            base["summary"] = _tokens(res.data.summary.strip(), numbered)
            base["agree"] = [_tokens(x.strip(), numbered) for x in res.data.agree if x.strip()][:8]
            base["differ"] = [_tokens(x.strip(), numbered) for x in res.data.differ if x.strip()][:8]
        return AgentResult(output=base)


def _left_out(answers: Any) -> list[str]:
    """Citations a member gave that could not be verified against the record or the verified authorities."""
    out: list[str] = []
    for o in answers:
        cites = list(o.get("cites", [])) + [c for side in ("claimant", "defendant") for p in o.get(side, []) for c in p.get("cites", [])]
        for c in cites:
            if c.get("status") != "verified":
                item = f"{c.get('text', '')} — {c.get('note', '')}".strip(" —")
                if item and item not in out:
                    out.append(item)
    return out[:12]
