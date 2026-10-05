"""Stage 2a — Fact extractor, one instance per document (parallel fan-out).

Long documents are split into chunks that are processed in parallel inside
the step; results are merged. Each fact carries the pinpoint reference
within its document so it can later be cited and verified.
"""

from __future__ import annotations

import asyncio

from app.agents.base import AgentContext, AgentResult
from app.agents.schemas import ExtractedFact, FactsOutput

SYSTEM = """You extract a dated factual chronology from ONE document filed in DIFC Courts proceedings.
Rules:
- Extract every event that has a date (or a month/year) and matters to the dispute: contracts, notices,
  instructions, payments, deliveries, meetings, breaches, terminations, applications, hearings, orders.
- asserted_by: 'Claimant' or 'Defendant' if this document is that party's pleading/statement and the
  fact is their assertion; 'Court' for orders and judgments; 'Document' for neutral contemporaneous records
  (contracts, letters, certificates, minutes).
- position: for party assertions, the party's version in one sentence in their terms (e.g. "The Employer
  instructed a revised curtain-wall system — VO-07, worth USD 3.9m"). Empty for neutral records.
- ref: the pinpoint copied exactly from the ⟦…⟧ tag of the segment the fact comes from, WITHOUT the
  document label — e.g. 'p. 12' or '¶ 19'.
- Never infer facts that are not in the text. Merge duplicates within this document.
- Return at most 60 facts; prefer the ones that matter most to liability."""


class FactsAgent:
    name = "facts"

    async def run(self, ctx: AgentContext) -> AgentResult:
        doc_id = ctx.key
        ingest = await ctx.output_of("ingest", doc_id or "")
        if not ingest:
            return AgentResult(output=FactsOutput(doc_id=doc_id or "", facts=[]).model_dump())
        label = ingest.get("label") or ingest.get("doc_type") or "Document"
        header = f"DOCUMENT: {label} | type: {ingest.get('doc_type')} | filed by: {ingest.get('filed_by')} | date: {ingest.get('doc_date')}\n"
        chunks = _chunks(ingest.get("segments", []), label, ctx.settings.doc_chunk_chars)

        async def one(chunk: str):
            res = await ctx.llm.generate(
                schema=FactsOutput, system=SYSTEM, tier="flash", temperature=0.1,
                contents=[header + chunk],
            )
            ctx.track(res)
            return res.data.facts

        results = await asyncio.gather(*(one(c) for c in chunks))
        facts = _dedupe([f for part in results for f in part])
        return AgentResult(output=FactsOutput(doc_id=doc_id or "", label=label, facts=facts).model_dump())


def _chunks(segments: list[dict], label: str, size: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    used = 0
    for seg in segments:
        line = f"⟦{label}, {seg['ref']}⟧ {seg['text']}\n"
        if cur and used + len(line) > size:
            chunks.append("".join(cur))
            cur, used = [], 0
        cur.append(line[:size])
        used += len(line)
    if cur:
        chunks.append("".join(cur))
    return chunks or [""]


def _dedupe(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    seen: set[tuple[str, str]] = set()
    out: list[ExtractedFact] = []
    for f in sorted(facts, key=lambda f: f.date_iso):
        k = (f.date_iso, f.title.strip().lower())
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out
