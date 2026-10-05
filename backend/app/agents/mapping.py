"""Stage 4 — Mapping (one instance per legal issue, parallel).

For the group of facts an issue turns on, finds the judgments and orders that
deal with them: this case's own orders from the record, plus external
authority found with Grounding with Google Search. Every external decision
must carry a URL from the search results; the verifier later drops any that
cannot be traced to a grounding source.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.corpus import COURT, labelled, render_corpus
from app.agents.schemas import MappingOutput
from app.harness.resilience import PermanentStepError

SYSTEM = """You are a legal researcher for a DIFC Courts judge. Map ONE group of facts to the decisions that deal with them.
Use Google Search. Prioritise, in order:
  1. Orders and judgments already made in THIS case (from the case record provided) — relation 'This case'
     (or 'Reserved'), from_case_record=true, url ''.
  2. DIFC Courts judgments (difccourts.ae) — Court of Appeal decisions are 'Binding'; first-instance decisions
     'Applied' if directly on point.
  3. English & Commonwealth authorities routinely followed in the DIFC (bailii.org,
     caselaw.nationalarchives.gov.uk, supremecourt.uk) — 'Persuasive' or 'Followed in DIFC'.
  4. Other jurisdictions only if squarely relevant — 'Persuasive · non-DIFC'.
Mark an authority 'Doubted' if a later decision has doubted it.
For every external decision give the exact URL of the judgment page from your search results. Do not cite
any case you did not find in the search results. Give the neutral citation, the court, and the date of
decision. 'how' explains in one or two sentences how it bears on THESE facts. Return 1–5 decisions."""


class MappingAgent:
    name = "mapping"

    async def run(self, ctx: AgentContext) -> AgentResult:
        n = int(ctx.key or 0)
        issues = (await ctx.output("issues")) or {"issues": []}
        issue = next((i for i in issues["issues"] if i["n"] == n), None)
        if issue is None:
            raise PermanentStepError(f"issue {n} not found")
        entries = ((await ctx.output("chronology")) or {"entries": []})["entries"]
        facts = [entries[i] for i in issue["fact_indices"] if i < len(entries)]
        facts_txt = "\n".join(f"- {f['date_text']}: {f['title']} — {f['common']}" for f in facts) or "(no linked facts)"

        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
        docs = labelled(await ctx.outputs("ingest"), (run or {}).get("doc_ids"))
        orders = render_corpus(docs, budget=120_000, include=COURT) if any(d.get("doc_type") in COURT for d in docs) else "(none)"
        case = await ctx.repo.get_case(ctx.case_id) or {}

        prompt = (
            f"CASE: {case.get('title', '')} ({case.get('no', '')}) — {case.get('type', '')}\n\n"
            f"ISSUE {n} · {issue['topic']}: {issue['question']}\nLaw engaged: {issue['law']}\n\n"
            f"FACTS IN THIS GROUP\n{facts_txt}\n\nORDERS AND JUDGMENTS IN THIS CASE'S RECORD\n{orders}"
        )
        res = await ctx.llm.generate(
            schema=MappingOutput, system=SYSTEM, tier="pro", search=True, temperature=0.2, contents=[prompt],
        )
        ctx.track(res)
        out = res.data
        out.issue = n
        out.search_queries = res.grounding.queries
        out.sources = res.grounding.sources
        return AgentResult(output=out.model_dump())
