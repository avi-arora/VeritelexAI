"""Stage 5a — Grounding coverage (one instance per legal issue, parallel with Mapping).

Queries the connected grounding source — currently Grounding with Google
Search only — for each issue and assesses how well it covers the issue
(full / partial / none), with the most relevant authorities found.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.schemas import CoverageDraft, CoverageOutput
from app.harness.resilience import PermanentStepError

SYSTEM = """You assess how well web search grounds one legal issue in a DIFC Courts case.
Search Google for authority and official material on the issue: DIFC Courts judgments (difccourts.ae), DIFC laws
and the Rules of the DIFC Courts, practice directions, and English authorities followed in the DIFC
(bailii.org, caselaw.nationalarchives.gov.uk). Law-firm commentary may be noted but is never authority.
coverage:
  'full'    — binding or directly on-point authority was found,
  'partial' — only general, procedural or persuasive material was found,
  'none'    — nothing authoritative was found.
note: one sentence saying what the search returned for this issue.
authorities: up to 4 of the most relevant authorities actually found, as 'Name [citation]' or 'site — title'."""


class GroundingAgent:
    name = "grounding"

    async def run(self, ctx: AgentContext) -> AgentResult:
        n = int(ctx.key or 0)
        issues = (await ctx.output("issues")) or {"issues": []}
        issue = next((i for i in issues["issues"] if i["n"] == n), None)
        if issue is None:
            raise PermanentStepError(f"issue {n} not found")
        case = await ctx.repo.get_case(ctx.case_id) or {}
        prompt = (
            f"Case type: {case.get('type', '')}. Court: DIFC Courts ({case.get('division', '')}).\n"
            f"ISSUE {n} · {issue['topic']}: {issue['question']}\nLaw engaged: {issue['law']}"
        )
        res = await ctx.llm.generate(
            schema=CoverageDraft, system=SYSTEM, tier="flash", search=True, temperature=0.1, contents=[prompt],
        )
        ctx.track(res)
        d = res.data
        out = CoverageOutput(
            issue=n, coverage=d.coverage if res.grounding.sources else "none",
            note=d.note if res.grounding.sources else "The search returned no grounded sources for this issue.",
            authorities=d.authorities[:4], search_queries=res.grounding.queries, sources=res.grounding.sources,
        )
        return AgentResult(output=out.model_dump())
