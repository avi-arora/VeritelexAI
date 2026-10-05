"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { TONE, type ChronoEntry, type Tone } from "@/lib/data";
import { Badge, Dot, GroundTags, Segmented, card, cx } from "../ui";
import { ReportGate } from "./case-context";

type View = "side" | "c" | "d" | "common";

const VIEWS = [
  { k: "side", label: "Side by side" },
  { k: "c", label: "As per the Claimant" },
  { k: "d", label: "As per the Defendant" },
  { k: "common", label: "Common · AI-grounded" },
] as const;

const VIEW_NOTE: Record<View, [string, string]> = {
  side: ["Each date shows what the Claimant pleads, what the Defendant pleads, and the common position grounded in the documents. Green ticks show the documents that ground it.", "#2E6B4F"],
  c: ["The Claimant’s chronology, from the Particulars of Claim and the Reply. The right-hand column shows how the Defendant responds to each entry.", "#245C86"],
  d: ["The Defendant’s chronology, from the Defence. The right-hand column shows how the Claimant responds to each entry.", "#8a8378"],
  common: ["Facts grounded in the documents on file. Where the parties disagree, the common entry records only what the documents show.", "#2E6B4F"],
};

export function Matrix() {
  return <ReportGate section="matrix">{(m) => <MatrixBody chronology={m.entries} />}</ReportGate>;
}

function MatrixBody({ chronology }: { chronology: ChronoEntry[] }) {
  const [view, setView] = useState<View>("side");
  const [disputedOnly, setDisputedOnly] = useState(false);
  const rows = chronology.filter((r) => !disputedOnly || r.tone === "red" || r.side !== "both");
  const [note, dot] = VIEW_NOTE[view];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented options={VIEWS} value={view} onChange={setView} itemClassName="h-9 px-3.5 text-[13.5px]" />
        <button
          type="button"
          aria-pressed={disputedOnly}
          onClick={() => setDisputedOnly((v) => !v)}
          className="flex h-9 items-center gap-2 rounded-[18px] border px-3.5 text-[13px] font-medium"
          style={{
            borderColor: disputedOnly ? "#ecc9c4" : "#dcd8d2",
            background: disputedOnly ? "#f8eae8" : "#fff",
            color: disputedOnly ? "#9B3E35" : "#3d434a",
          }}
        >
          <Dot color="#9B3E35" size={9} />
          Disputed or one-sided only
        </button>
      </div>
      <div className="flex items-start gap-3 rounded-[10px] border border-line bg-white px-[18px] py-3.5">
        <Dot color={dot} size={8} style={{ marginTop: 7 }} />
        <span className="text-sm leading-[1.6] text-body-3">{note}</span>
      </div>

      <div className={cx(card, "overflow-x-auto")}>
        {view === "side" && <SideBySide rows={rows} />}
        {(view === "c" || view === "d") && <PartyView rows={rows} party={view} />}
        {view === "common" && <CommonView rows={rows} />}
      </div>
    </div>
  );
}

const SIDE_COLS = "grid grid-cols-[118px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)] min-w-[820px]";

function SideBySide({ rows }: { rows: ChronoEntry[] }) {
  return (
    <>
      <div className={cx(SIDE_COLS, "border-b border-line-2 bg-panel")}>
        <span className="px-[18px] py-3.5 text-[12.5px] font-medium text-muted">Date</span>
        <ColHead color="#245C86" square>As per the Claimant</ColHead>
        <ColHead color="#8a8378" square>As per the Defendant</ColHead>
        <ColHead color="#2E6B4F" className="bg-[#f1f6f2]">Common · AI-grounded</ColHead>
      </div>
      {rows.map((r) => (
        <div key={`${r.i}-${r.d}-${r.t}`} className={cx(SIDE_COLS, "border-b border-line-3")}>
          <div className="flex flex-col gap-1.5 p-[18px]">
            <span className="font-mono text-[13.5px] font-medium text-ink">{r.d}</span>
            <span className="text-[12.5px] leading-[1.4] text-muted">{issueText(r.iss)}</span>
          </div>
          <Pleading text={r.cv} cite={r.cRef} missing="Not pleaded by the Claimant" />
          <Pleading text={r.dv} cite={r.dRef} missing="Not pleaded by the Defendant" />
          <div className="flex flex-col gap-[9px] border-l border-line-3 bg-[#fafcfb] p-[18px]">
            <div className="flex items-start justify-between gap-2.5">
              <span className="font-serif text-[15px] leading-[1.4] font-semibold text-ink">{r.t}</span>
              <Badge tone={r.tone} className="flex-none px-2 py-[3px] text-[11.5px] whitespace-nowrap">{r.st}</Badge>
            </div>
            <span className="text-[13.5px] leading-[1.6] text-body-2">{r.b}</span>
            <GroundTags items={r.ground} />
          </div>
        </div>
      ))}
    </>
  );
}

function ColHead({ color, square, className, children }: { color: string; square?: boolean; className?: string; children: string }) {
  return (
    <span className={cx("flex items-center gap-2 border-l border-line-2 px-[18px] py-3.5 text-[13px] font-semibold text-ink", className)}>
      <Dot color={color} square={square} />
      {children}
    </span>
  );
}

function Pleading({ text, cite, missing }: { text: string; cite: string; missing: string }) {
  return (
    <div className={cx("flex flex-col gap-2 border-l border-line-3 p-[18px]", text ? "bg-white" : "bg-panel")}>
      <span className="font-serif text-[14.5px] leading-[1.6]" style={{ color: text ? "#2a2f35" : "#a4a09a" }}>{text || missing}</span>
      {text && <span className="text-[12.5px] text-blue">{cite}</span>}
    </div>
  );
}

function PartyView({ rows, party }: { rows: ChronoEntry[]; party: "c" | "d" }) {
  const isC = party === "c";
  return (
    <>
      {rows
        .filter((r) => (isC ? r.cv : r.dv))
        .map((r) => {
          const other = isC ? r.dv : r.cv;
          const [rel, tone]: [string, Tone] =
            r.side !== "both" ? ["Not addressed by the other side", "grey"]
            : r.tone === "red" ? ["Disputed by the other side", "red"]
            : r.tone === "blue" || r.tone === "amber" ? ["Court record", "blue"]
            : ["Accepted by the other side", "green"];
          return (
            <div key={`${r.i}-${r.d}-${r.t}`} className="grid min-w-[700px] grid-cols-[120px_minmax(0,1fr)_210px] items-start gap-5 border-b border-line-3 px-6 py-5">
              <span className="pt-px font-mono text-sm font-medium text-ink">{r.d}</span>
              <div className="flex min-w-0 flex-col gap-1.5 border-l-[3px] pl-3.5" style={{ borderColor: isC ? "#245C86" : "#8a8378" }}>
                <span className="font-serif text-base leading-[1.4] font-semibold text-ink">{r.t}</span>
                <span className="font-serif text-[15px] leading-[1.6] text-prose">{isC ? r.cv : r.dv}</span>
                <span className="text-[12.5px] text-blue">{isC ? r.cRef : r.dRef}</span>
              </div>
              <div className="flex flex-col items-end gap-2 text-right">
                <Badge tone={tone} className="px-[9px] py-1 text-xs">{rel}</Badge>
                {other && <span className="text-[13px] leading-normal text-muted">{(isC ? "Defendant: " : "Claimant: ") + other}</span>}
              </div>
            </div>
          );
        })}
    </>
  );
}

function CommonView({ rows }: { rows: ChronoEntry[] }) {
  const { caseId } = useParams<{ caseId: string }>();
  return (
    <>
      {rows.map((r) => {
        const n = r.mapped ?? 0;
        const fg = TONE[r.tone].fg;
        return (
          <div key={`${r.i}-${r.d}-${r.t}`} className="grid min-w-[640px] grid-cols-[120px_20px_minmax(0,1fr)_150px] items-start gap-4 border-b border-line-3 px-6 py-5">
            <span className="pt-px font-mono text-sm font-medium text-ink">{r.d}</span>
            <Dot color={fg} style={{ marginTop: 6 }} />
            <div className="flex min-w-0 flex-col gap-[7px]">
              <span className="font-serif text-base leading-[1.4] font-semibold text-ink">{r.t}</span>
              <span className="text-pretty text-sm leading-[1.6] text-body-3">{r.b}</span>
              <div className="mt-0.5">
                <GroundTags items={r.ground} />
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge tone={r.tone} className="px-[9px] py-1 text-xs whitespace-nowrap">{r.st}</Badge>
              {n > 0 && (
                <Link href={`/cases/${caseId}/mapping`} className="text-[12.5px] font-medium whitespace-nowrap">
                  {n === 1 ? "1 decision" : `${n} decisions`} →
                </Link>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}

function issueText(iss: number[]) {
  return iss.length ? "Issue " + iss.join(", ") : "";
}
