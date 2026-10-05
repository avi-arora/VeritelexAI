"""Stage 1 — Background agent (runs in parallel with fact extraction).

Produces everything on the Background screen and the "Confirm case details"
step of the upload wizard: case profile fields (each with its source),
plain-English background paragraphs, key facts and the case-header subtitle.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.corpus import labelled, render_corpus
from app.agents.schemas import BackgroundOutput
from app.harness.resilience import PermanentStepError

SYSTEM = """You are a senior judicial assistant at the DIFC Courts preparing a bench brief.
Read the case record and produce:
1. The case profile. For every field give the value and where it was found, written like
   "From Claim Form, page 1" or "From Particulars of Claim ¶1". If a value is inferred rather than
   stated, say "Suggested from the pleadings". Division is one of: Court of First Instance,
   Technology & Construction, Arbitration, Digital Economy Court, Small Claims Tribunal, Court of Appeal.
   Amount claimed keeps its currency (e.g. "AED 9,420,000" or "USD 48.2m").
2. Two to four short paragraphs of background in plain, neutral English: the transaction, what went wrong
   and each side's core position, then the procedural position (what has been decided, what is listed).
   Never take sides. Never invent facts — everything must come from the record.
3. Six key facts with these labels: Claimant, Defendant, Contract, Amount claimed, Stage, Presiding.
   Use "Not stated in the record" when the record is silent.
4. A one-line subtitle: "<Division> · <subject> · <amount> claimed".
Write party names exactly as they appear in the pleadings."""


class BackgroundAgent:
    name = "background"

    async def run(self, ctx: AgentContext) -> AgentResult:
        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
        docs = labelled(await ctx.outputs("ingest"), (run or {}).get("doc_ids"))
        if not docs:
            raise PermanentStepError("no document could be read", "None of the uploaded documents could be read")
        corpus = render_corpus(docs, budget=min(ctx.settings.corpus_budget_chars, 600_000))
        res = await ctx.llm.generate(
            schema=BackgroundOutput, system=SYSTEM, tier="pro", temperature=0.1,
            contents=[f"CASE RECORD\n\n{corpus}"],
        )
        ctx.track(res)
        out = res.data
        p = out.profile
        fields = [
            {"k": "Claim number", "v": p.claim_number.value, "src": p.claim_number.source, "full": False},
            {"k": "Division", "v": p.division.value, "src": p.division.source, "full": False},
            {"k": "Case title", "v": p.title.value, "src": p.title.source, "full": True},
            {"k": "Claimant", "v": p.claimant.value, "src": p.claimant.source, "full": False},
            {"k": "Defendant", "v": p.defendant.value, "src": p.defendant.source, "full": False},
            {"k": "Case type", "v": p.case_type.value, "src": p.case_type.source, "full": False},
            {"k": "Amount claimed", "v": p.amount_claimed.value, "src": p.amount_claimed.source, "full": False},
        ]
        case = await ctx.repo.get_case(ctx.case_id) or {}
        if not case.get("confirmed"):
            # Surface the extracted details immediately (upload step 2 polls for them).
            await ctx.repo.update_case(ctx.case_id, {
                "no": p.claim_number.value or case.get("no"), "title": p.title.value or case.get("title"),
                "type": p.case_type.value, "division": p.division.value, "subtitle": out.subtitle,
                "fields": fields, "claimant": p.claimant.value, "defendant": p.defendant.value,
            })
        return AgentResult(output={**out.model_dump(), "fields": fields})
