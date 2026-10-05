"""Stage 3 — Legal issues (sequential: needs the chronology).

Frames the questions the Court must answer from the statements of case,
reconciles them with orders already made (status), and links each issue to
the chronology entries it turns on. Its output drives the per-issue fan-out
of the Mapping and Grounding agents.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.corpus import COURT, PLEADINGS, labelled, render_corpus
from app.agents.schemas import IssuesOutput

SYSTEM = """You are a judicial assistant at the DIFC Courts framing the legal issues for the judge.
From the statements of case, skeletons, applications and orders:
- Identify the 3–10 distinct questions of law or mixed fact and law the Court must answer. Phrase each as a
  single neutral question a judge would write (e.g. "Is the cl. 20.1 notice a condition precedent to an
  extension of time, and was it given in time?").
- topic: one or two words. law: the contract clauses, DIFC laws, RDC rules or doctrines engaged.
- status: 'decided' if an order or judgment in the record has determined it (status_text like
  'Decided · Order 3'), 'reserved' if heard with judgment reserved ('Reserved · Order 7'), else 'for_trial'
  ('For trial').
- fact_indices: the indices [i] of the chronology entries the issue turns on.
Number issues from 1 in the logical order a judgment would address them. Use only the record."""


class IssuesAgent:
    name = "issues"

    async def run(self, ctx: AgentContext) -> AgentResult:
        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
        docs = labelled(await ctx.outputs("ingest"), (run or {}).get("doc_ids"))
        chron = (await ctx.output("chronology")) or {"entries": []}
        entries = chron["entries"]
        chron_txt = "\n".join(
            f"[{i}] {e['date_text']} — {e['title']} ({e['status']}): {e['common']}" for i, e in enumerate(entries)
        )
        corpus = render_corpus(docs, budget=min(ctx.settings.corpus_budget_chars, 600_000), include=PLEADINGS | COURT)
        res = await ctx.llm.generate(
            schema=IssuesOutput, system=SYSTEM, tier="pro", temperature=0.1,
            contents=[f"CHRONOLOGY\n{chron_txt or '(empty)'}\n\nSTATEMENTS OF CASE AND ORDERS\n{corpus}"],
        )
        ctx.track(res)
        issues = []
        for n, iss in enumerate(res.data.issues, start=1):
            iss.n = n
            iss.fact_indices = sorted({i for i in iss.fact_indices if 0 <= i < len(entries)})
            issues.append(iss)
        return AgentResult(output=IssuesOutput(issues=issues).model_dump(), fanout=[str(i.n) for i in issues])
