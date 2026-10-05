"""Stage 6 — Finalize: assemble agent outputs into the exact shapes the UI
renders, publish report sections, and mark the case ready.

Optional upstream steps may be missing (degraded run); every section is
built defensively so a partial run still produces a usable report.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base import AgentContext, AgentResult
from app.agents.council import council_sections
from app.agents.record import kept_decisions
from app.domain.models import (
    BackgroundSection,
    ChronoEntry,
    Decision,
    GroundingSection,
    GroundSource,
    IssueOut,
    IssuesSection,
    KeyFact,
    MappingGroup,
    MappingSection,
    MatrixSection,
)

STATUS_TONE = {"Agreed": "green", "Disputed": "red", "One side only": "grey", "Decided": "blue", "Reserved": "amber"}
ISSUE_TONE = {"decided": "blue", "reserved": "amber", "for_trial": "grey"}
REL_TONE = {
    "This case": "blue", "Binding": "blue", "Applied": "green", "Followed in DIFC": "green",
    "Persuasive": "grey", "Persuasive · non-DIFC": "grey", "Doubted": "red", "Reserved": "amber",
}


def via_for(url: str, from_record: bool) -> str:
    if from_record:
        return "Case record"
    host = url.lower()
    if "difccourts.ae" in host:
        return "DIFC Courts Judgments · Google Search"
    if "bailii.org" in host:
        return "BAILII · Google Search"
    if "nationalarchives.gov.uk" in host:
        return "Find Case Law · Google Search"
    return "Google Search"


class FinalizeAgent:
    name = "finalize"

    async def run(self, ctx: AgentContext) -> AgentResult:
        bg = await ctx.output("background") or {}
        chron = (await ctx.output("chronology") or {}).get("entries", [])
        issues = (await ctx.output("issues") or {}).get("issues", [])
        mappings = await ctx.outputs("mapping")
        grounds = await ctx.outputs("grounding")
        verify = await ctx.output("verify")
        docs = await ctx.repo.list_documents(ctx.case_id)
        run = await ctx.repo.get_run(ctx.case_id, ctx.run_id) or {}
        run_docs = [d for d in docs if d["id"] in set(run.get("doc_ids", []))]

        # ---- issues ↔ facts --------------------------------------------------
        fact_issues: dict[int, list[int]] = {}
        for iss in issues:
            for i in iss.get("fact_indices", []):
                fact_issues.setdefault(i, []).append(iss["n"])

        # ---- mapping ----------------------------------------------------------
        groups: list[MappingGroup] = []
        mapped_count: dict[int, int] = {}
        excluded = 0
        for iss in issues:
            m = mappings.get(str(iss["n"]))
            if not m:
                continue
            decisions = m.get("decisions", [])
            keep, hrefs = kept_decisions(decisions, verify, iss["n"])
            excluded += len(decisions) - len(keep)
            out_dec = []
            for i, href in zip(keep, hrefs):
                d = decisions[i]
                out_dec.append(Decision(
                    name=d["name"], cite=d["cite"], court=d["court"], date=d["date"], rel=d["relation"],
                    tone=REL_TONE.get(d["relation"], "grey"), how=d["how"],
                    via=via_for(href, d.get("from_case_record", False)), href=href or "",
                ))
            if not out_dec:
                continue
            fidx = [i for i in iss.get("fact_indices", []) if i < len(chron)]
            dates = [chron[i]["date_text"] for i in fidx]
            span = " · ".join(dict.fromkeys([dates[0], dates[-1]])) if dates else ""
            for i in fidx:
                mapped_count[i] = mapped_count.get(i, 0) + len(out_dec)
            groups.append(MappingGroup(facts=fidx, d=span, t=m.get("title") or iss["topic"], iss=f"Issue {iss['n']}", decisions=out_dec))
        total_decisions = sum(len(g.decisions) for g in groups)

        # ---- matrix -----------------------------------------------------------
        entries: list[ChronoEntry] = []
        for i, e in enumerate(chron):
            ground = verify["ground_kept"][i] if verify and i < len(verify["ground_kept"]) else e.get("ground", [])
            ok = verify["chronology_verified"][i] if verify and i < len(verify["chronology_verified"]) else True
            entries.append(ChronoEntry(
                d=e["date_text"], t=e["title"], b=e["common"], st=e["status"], tone=STATUS_TONE.get(e["status"], "grey"),
                iss=sorted(fact_issues.get(i, [])), cv=e.get("claimant_view", ""), cRef=e.get("claimant_ref", ""),
                dv=e.get("defendant_view", ""), dRef=e.get("defendant_ref", ""), ground=ground, side=e.get("side", "both"),
                i=i, mapped=mapped_count.get(i, 0), verified=bool(ok),
            ))

        # ---- issues section --------------------------------------------------
        issues_out = [
            IssueOut(
                n=x["n"], topic=x["topic"], q=x["question"], law=x["law"], st=x["status_text"],
                tone=ISSUE_TONE.get(x["status_kind"], "grey"),
                facts=" · ".join(chron[i]["date_text"] for i in x.get("fact_indices", []) if i < len(chron)) or "—",
            )
            for x in issues
        ]

        # ---- grounding --------------------------------------------------------
        cov: list[tuple[str, str]] = []
        auth: list[str] = []
        pages_read: set[str] = set()
        cited = 0
        for x in issues:
            g = grounds.get(str(x["n"]))
            if g:
                cov.append((g["coverage"], g["note"]))
                auth += [a for a in g.get("authorities", []) if a not in auth]
                pages_read |= {s["uri"] for s in g.get("sources", [])}
            else:
                cov.append(("none", "Grounding did not complete for this issue."))
        for m in mappings.values():
            pages_read |= {s["uri"] for s in m.get("sources", [])}
        cited = total_decisions
        covered = sum(c != "none" for c, _ in cov)
        sources = {
            "google": GroundSource(
                short="Google", type="Web search",
                meta=f"Grounded search · {len(pages_read)} pages read · {cited} cited",
                sum=(f"Grounding with Google Search covered {covered} of {len(cov)} issues. Results favour DIFC Courts "
                     "judgments and official sources; commentary is shown but never relied on as authority."),
                auth=auth[:4], cov=cov,  # type: ignore[arg-type]
            )
        }

        # ---- background ------------------------------------------------------
        counts = {"facts": len(entries), "decisions": total_decisions, "issues": len(issues_out), "gaps": 0}
        background = BackgroundSection(
            paragraphs=bg.get("paragraphs", []),
            keyFacts=[KeyFact(k=k["label"], v=k["value"]) for k in bg.get("key_facts", [])],
            fields=bg.get("fields", []),
            counts=counts,
        )

        sections: dict[str, Any] = {
            "background": background.model_dump(),
            "matrix": MatrixSection(entries=entries).model_dump(),
            "mapping": MappingSection(groups=groups, totalDecisions=total_decisions, excluded=excluded).model_dump(),
            "issues": IssuesSection(issues=issues_out).model_dump(),
            "tools": GroundingSection(sources=sources, verification=(verify or {}).get("stats", {})).model_dump(),
        }
        council_summary: list[dict[str, Any]] = []
        built = await council_sections(ctx, issues, run)
        if built:
            sections["council"], sections["questions"], council_summary = built
        for name, data in sections.items():
            await ctx.repo.put_report(ctx.case_id, name, ctx.run_id, data)

        # ---- version summary (read by the versions list) ----------------------
        ready_at = datetime.now(UTC)
        await ctx.repo.update_run(ctx.case_id, ctx.run_id, {
            "report_ready_at": ready_at, "sections": list(sections), "doc_count": len(run_docs),
            "counts": {"facts": len(entries), "issues": len(issues_out), "decisions": total_decisions},
            "council": council_summary,
        })

        # ---- case summary ----------------------------------------------------
        pages = sum(int(d.get("pages") or 0) for d in run_docs)
        unreadable = [d for d in run_docs if d.get("status") in ("unreadable", "failed")]
        today = ready_at.strftime("%d %b %Y")
        note = f"Report generated {today} · {len(entries)} dated facts · {len(issues_out)} issues"
        if unreadable:
            note += f" · {len(unreadable)} document{'s' if len(unreadable) > 1 else ''} partly unreadable"
        case = await ctx.repo.get_case(ctx.case_id) or {}
        if case.get("latest_run_id") == ctx.run_id:
            await ctx.repo.update_case(ctx.case_id, {
                "status": "ready", "pct": 100, "at": None, "note": note, "report_run_id": ctx.run_id,
                "report_ready_at": ready_at, "doc_count": len(run_docs), "page_count": pages,
            })
        return AgentResult(output={"sections": list(sections), "counts": counts})
