"""Stage 2b — Chronology merge (join over every per-document fact list).

Merges facts from all documents into one date-ordered chronology with each
party's pleaded version side by side and a neutral, document-grounded common
entry — the "Dates and facts" screen.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.corpus import labelled
from app.agents.schemas import ChronologyOutput

SYSTEM = """You build the factual matrix for a DIFC Courts judge from facts extracted from every document on file.
Merge facts that describe the same event into ONE entry. For each entry:
- claimant_view / defendant_view: each party's pleaded version (from facts asserted_by that party), with
  claimant_ref / defendant_ref as '<Document label>, <ref>' exactly as given. Leave empty if not pleaded.
- common: what the documents themselves show, neutrally. Where the parties disagree, record only what is
  not in dispute and state precisely what is disputed.
- status: 'Agreed' (both accept or neutral documents establish it unchallenged), 'Disputed' (the parties
  contradict each other), 'One side only' (only one party pleads it), 'Decided' (an order or judgment of the
  Court determined it), 'Reserved' (heard, judgment reserved).
- side: 'both' unless only the claimant ('c') or only the defendant ('d') pleads it.
- ground: the document citations '<Document label>, <ref>' (copied exactly from the facts list) that
  establish the common entry. Prefer contemporaneous documents and orders over pleadings.
Keep the 15–60 facts that matter to liability, sorted by date. Never invent facts, dates or citations."""


class ChronologyAgent:
    name = "chronology"

    async def run(self, ctx: AgentContext) -> AgentResult:
        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
        docs = {d["doc_id"]: d for d in labelled(await ctx.outputs("ingest"), (run or {}).get("doc_ids"))}
        facts_by_doc = await ctx.outputs("facts")

        lines: list[str] = []
        n = 0
        for doc_id, fo in facts_by_doc.items():
            d = docs.get(doc_id)
            if not d:
                continue
            for f in fo.get("facts", []):
                n += 1
                pos = f" | position: {f['position']}" if f.get("position") else ""
                lines.append(
                    f"[F{n}] {f['date_iso']} ({f['date_text']}) | {d['cite_label']}, {f['ref']} | "
                    f"{d.get('doc_type')} filed by {d.get('filed_by')} | asserted by {f['asserted_by']} | "
                    f"{f['title']}: {f['description']}{pos}"
                )
        if not lines:
            return AgentResult(output=ChronologyOutput(entries=[]).model_dump())

        res = await ctx.llm.generate(
            schema=ChronologyOutput, system=SYSTEM, tier="pro", temperature=0.1, max_output_tokens=65_536,
            contents=["EXTRACTED FACTS (one per line)\n" + "\n".join(lines)],
        )
        ctx.track(res)
        entries = sorted(res.data.entries, key=lambda e: e.date_iso)
        return AgentResult(output=ChronologyOutput(entries=entries).model_dump())
