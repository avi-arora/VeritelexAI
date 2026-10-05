"use client";

import Link from "next/link";
import { useState } from "react";
import type { IssueData, ToolsData } from "@/lib/api";
import { CONNECTORS, COV, TONE, type ConnectorId } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Badge, Dot, Monogram, btn, card, cx } from "../ui";
import { ReportGate, useReport } from "./case-context";

export function Grounding() {
  const { data: iss } = useReport("issues");
  return <ReportGate section="tools">{(tools) => <GroundingBody tools={tools} issues={iss?.issues ?? []} />}</ReportGate>;
}

function GroundingBody({ tools, issues: ISSUES }: { tools: ToolsData; issues: IssueData[] }) {
  const { conn } = useStore();
  const [selected, setSelected] = useState<ConnectorId>("google");
  const GROUND = tools.sources as Partial<Record<ConnectorId, ToolsData["sources"][string]>>;

  // Only connectors that are available, enabled and actually returned results for this case.
  const sources = CONNECTORS.filter((c) => c.available && conn[c.id] && GROUND[c.id]);
  const sel = sources.find((c) => c.id === selected) ?? sources[0];
  if (!sel) return <div className={cx(card, "px-7 py-6 text-sm text-body-3")}>No grounding source is connected for this case.</div>;
  const detail = GROUND[sel.id]!;
  const cols = `minmax(200px,1.6fr) repeat(${sources.length}, minmax(92px,1fr))`;

  return (
    <div className="flex flex-col gap-5">
      <div className={cx(card, "flex flex-wrap items-center gap-[18px] px-[22px] py-[18px]")}>
        <div className="flex min-w-[260px] flex-1 flex-col gap-1">
          <span className="text-[15px] font-semibold text-ink">{sources.length} grounding sources queried for this case</span>
          <span className="text-[13.5px] leading-normal text-muted">
            Select a source to see what it returned on each issue. Every statement in the report cites one of these or the case record.
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3.5 text-[12.5px] text-body-3">
          <Legend color="#2E6B4F">Covered</Legend>
          <Legend color="#8F6A1E">Partly covered</Legend>
          <Legend color="#cfcbc4">Not covered</Legend>
        </div>
        <Link href="/settings/connectors" className={cx(btn.outline, "flex h-9 items-center px-3.5 text-[13px] text-ink hover:text-ink hover:no-underline")}>
          Manage sources
        </Link>
      </div>

      <div className={cx(card, "overflow-x-auto")}>
        <div style={{ minWidth: 200 + 92 * sources.length }}>
          <div className="grid border-b border-line-2 bg-panel" style={{ gridTemplateColumns: cols }}>
            <span className="self-end px-5 py-3.5 text-[12.5px] font-medium text-muted">Legal issue</span>
            {sources.map((c) => {
              const on = c.id === sel.id;
              const cov = GROUND[c.id]!.cov;
              return (
                <button
                  key={c.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSelected(c.id)}
                  className="flex flex-col items-center gap-[5px] border-b-2 px-1.5 pt-3 pb-2.5"
                  style={{ background: on ? "#eef3f8" : "transparent", borderColor: on ? "#245C86" : "transparent" }}
                >
                  <Monogram m={c.m} c={c.mono} size={28} radius={7} fontSize={10.5} />
                  <span className="text-center text-xs leading-[1.25] font-medium text-ink">{GROUND[c.id]!.short}</span>
                  <span className="text-[11.5px] text-muted">{cov.filter((x) => x[0] !== "none").length} of {cov.length}</span>
                </button>
              );
            })}
          </div>
          {ISSUES.map((iss, i) => (
            <div key={iss.n} className="grid border-b border-line-4" style={{ gridTemplateColumns: cols }}>
              <div className="flex items-baseline gap-2.5 px-5 py-3.5">
                <span className="flex-none font-serif text-[15px] font-semibold text-blue">{iss.n}</span>
                <span className="text-sm leading-[1.45] font-medium text-ink">{iss.topic}</span>
              </div>
              {sources.map((c) => {
                const [k, note] = GROUND[c.id]!.cov[i] ?? ["none", ""];
                const t = TONE[COV[k][2]];
                return (
                  <button
                    key={c.id}
                    type="button"
                    title={note}
                    onClick={() => setSelected(c.id)}
                    className="flex items-center justify-center px-1 py-2.5"
                    style={{ background: c.id === sel.id ? "#f6f9fc" : "transparent" }}
                  >
                    <Badge fg={k === "none" ? "#a3a8ae" : t.fg} bg={k === "none" ? "transparent" : t.bg}>{COV[k][1]}</Badge>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className={cx(card, "grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] overflow-hidden")}>
        <div className="flex flex-col gap-3 border-r border-line-2 bg-panel px-6 py-[22px]">
          <div className="flex items-center gap-3">
            <Monogram m={sel.m} c={sel.mono} />
            <div className="flex flex-col">
              <span className="text-base font-semibold text-ink">{sel.name}</span>
              <span className="text-[12.5px] text-muted">{detail.type} · {sel.by}</span>
            </div>
          </div>
          <span className="text-[12.5px] text-muted-2">{detail.meta}</span>
          <p className="text-pretty m-0 text-sm leading-[1.6] text-body-2">{detail.sum}</p>
          <div className="flex flex-col gap-1.5 border-t border-line-2 pt-3">
            <span className="text-xs font-medium text-muted">Most relevant results</span>
            {detail.auth.map((x) => (
              <span key={x} className="font-serif text-sm leading-[1.45] text-blue-dark italic">{x}</span>
            ))}
          </div>
        </div>
        <div className="flex flex-col">
          {ISSUES.map((iss, i) => {
            const [k, note] = detail.cov[i] ?? ["none", ""];
            return (
              <div key={iss.n} className="grid grid-cols-[minmax(0,180px)_minmax(0,1fr)] items-start gap-4 border-b border-line-4 px-6 py-3.5">
                <div className="flex flex-col items-start gap-1.5">
                  <span className="text-sm font-medium text-ink">{iss.n}. {iss.topic}</span>
                  <Badge tone={COV[k][2]}>{COV[k][0]}</Badge>
                </div>
                <span className="text-[13.5px] leading-[1.55] text-body-3">{note}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Legend({ color, children }: { color: string; children: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <Dot color={color} size={9} />
      {children}
    </span>
  );
}
