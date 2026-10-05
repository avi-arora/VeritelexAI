"""Stage 5b — Citation verifier (the grounding policy enforcer).

* Chronology: every ``ground`` citation must resolve to a real segment of the
  case record; unresolvable citations are dropped. A batched model check then
  confirms the cited text actually supports the common entry.
* Mapping: an external decision is kept only if its URL can be traced to the
  Google Search grounding sources returned for that issue (redirects resolved
  and compared), or it resolves on a host that the grounding returned.
  Decisions from this case's record are kept. Everything else is excluded
  ("Leave out unverified citations").
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agents.base import AgentContext, AgentResult
from app.agents.corpus import citation_index, labelled, resolve
from app.agents.schemas import SupportBatch, VerifyOutput
from app.agents.urlcheck import canon, host_of, make_client, resolve_url

SUPPORT_SYSTEM = """You check whether cited passages from a court record support statements in a chronology.
For each numbered item you get a statement and the text of the passages it cites. Answer:
'supported' — the passages establish the statement; 'partial' — they establish part of it;
'unsupported' — they do not. Judge only against the passages given."""

BATCH = 15


class VerifyAgent:
    name = "verify"

    async def run(self, ctx: AgentContext) -> AgentResult:
        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id)
        docs = labelled(await ctx.outputs("ingest"), (run or {}).get("doc_ids"))
        idx = citation_index(docs)
        entries = ((await ctx.output("chronology")) or {"entries": []})["entries"]
        stats = {"citations": 0, "citations_resolved": 0, "entries": len(entries), "entries_supported": 0,
                 "decisions": 0, "decisions_kept": 0}

        # ---- chronology citations -------------------------------------------
        ground_kept: list[list[str]] = []
        passages: list[str] = []
        for e in entries:
            kept, texts = [], []
            for c in e.get("ground", []):
                stats["citations"] += 1
                txt = resolve(c, idx)
                if txt:
                    kept.append(c)
                    texts.append(f"[{c}] {txt[:1500]}")
            stats["citations_resolved"] += len(kept)
            ground_kept.append(kept)
            passages.append("\n".join(texts))

        verdicts = ["unsupported"] * len(entries)
        todo = [i for i, k in enumerate(ground_kept) if k]

        async def check(batch: list[int]) -> None:
            body = "\n\n".join(
                f"ITEM {i}\nSTATEMENT: {entries[i]['title']} — {entries[i]['common']}\nPASSAGES:\n{passages[i]}" for i in batch
            )
            res = await ctx.llm.generate(schema=SupportBatch, system=SUPPORT_SYSTEM, tier="flash", temperature=0.0, contents=[body])
            ctx.track(res)
            for chk in res.data.checks:
                if chk.index in batch:
                    verdicts[chk.index] = chk.verdict

        await asyncio.gather(*(check(todo[i : i + BATCH]) for i in range(0, len(todo), BATCH)))
        verified = [v in ("supported", "partial") for v in verdicts]
        stats["entries_supported"] = sum(verified)

        # ---- mapping decisions ----------------------------------------------
        mappings = await ctx.outputs("mapping")
        kept_idx: dict[str, list[int]] = {}
        hrefs: dict[str, list[str]] = {}
        async with make_client(ctx.settings.url_check_timeout_s) as client:
            sem = asyncio.Semaphore(8)

            async def res_url(u: str) -> tuple[str | None, int | None]:
                async with sem:
                    return await resolve_url(u, client)

            async def check_mapping(m: dict[str, Any]) -> tuple[list[int], list[str]]:
                srcs: list[dict[str, Any]] = m.get("sources", [])
                resolved = await asyncio.gather(*(res_url(s["uri"]) for s in srcs))
                src_final: dict[str, str] = {}
                for s, (u, st) in zip(srcs, resolved, strict=True):
                    if u and st and st < 400:
                        src_final[canon(u)] = u
                        # The model may cite the grounding redirect URI itself.
                        src_final[canon(s["uri"])] = u
                src_hosts = {host_of(u) for u in src_final.values()} | {
                    (s.get("domain") or s.get("title") or "").lower().removeprefix("www.") for s in srcs
                }
                src_hosts.discard("")

                async def check_decision(d: dict[str, Any]) -> str | None:
                    """Verified href ("" for case-record items), or None to exclude."""
                    if d.get("from_case_record"):
                        return ""
                    url = (d.get("url") or "").strip()
                    if not url:
                        return None
                    if canon(url) in src_final:
                        return src_final[canon(url)]
                    if host_of(url) in src_hosts:
                        final, status = await res_url(url)
                        if final and status and status < 400:
                            return final
                    return None

                results = await asyncio.gather(*(check_decision(d) for d in m.get("decisions", [])))
                kept = [i for i, h in enumerate(results) if h is not None]
                return kept, [results[i] or "" for i in kept]

            keys = list(mappings)
            checked = await asyncio.gather(*(check_mapping(mappings[k]) for k in keys))
            for key, (kept, links) in zip(keys, checked, strict=True):
                kept_idx[key], hrefs[key] = kept, links
                stats["decisions"] += len(mappings[key].get("decisions", []))
                stats["decisions_kept"] += len(kept)

        out = VerifyOutput(
            chronology_verified=verified, ground_kept=ground_kept, decisions_kept=kept_idx,
            decision_hrefs=hrefs, stats=stats,
        )
        return AgentResult(output=out.model_dump())
