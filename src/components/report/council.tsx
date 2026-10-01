"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FLAGGED, MODELS, PRE, TONE, type Tone } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Badge, Button, Dot, Monogram, ReadingTag, Spinner, btn, card, cx } from "../ui";

/** Simulated council run: true for a moment after `run()` is called. */
export function useCouncilRun(ms = 1800) {
  const [running, setRunning] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const run = () => {
    clearTimeout(timer.current);
    setRunning(true);
    timer.current = setTimeout(() => setRunning(false), ms);
  };
  return [running, run] as const;
}

export function CouncilPreAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const { enabledIds: ids, nm } = useStore();
  const [running, run] = useCouncilRun();

  const heads = ids.map((id) => {
    const m = MODELS.find((x) => x.id === id)!;
    return { id, m: m.m, c: m.c, name: nm(id) };
  });
  const cols = `minmax(260px,2fr) repeat(${ids.length}, 48px) 128px`;

  const rows = PRE.map((p) => {
    const a = ids.filter((id) => p.votes[id] === "A").length;
    const b = ids.length - a;
    const unanimous = a === ids.length || b === ids.length;
    const [cons, tone]: [string, Tone] = unanimous ? ["Unanimous", "green"] : a === b ? [`Split ${a}–${b}`, "red"] : [`Majority ${Math.max(a, b)}–${Math.min(a, b)}`, "amber"];
    return {
      ...p,
      unanimous,
      majA: a >= b,
      cons,
      tone,
      aBy: ids.filter((id) => p.votes[id] === "A").map(nm).join(", "),
      bBy: ids.filter((id) => p.votes[id] === "B").map(nm).join(", "),
    };
  });
  const agree = rows.filter((r) => r.unanimous);
  const divides = rows.filter((r) => !r.unanimous);

  const stats = [
    { v: agree.length, l: "Issues agreed", s: "every model reads it the same way", c: "#2E6B4F" },
    { v: divides.length, l: "Issues where it divides", s: "majority or split", c: "#B07A18" },
    { v: FLAGGED.length, l: "Facts every model flagged", s: "decisive points in the record", c: "#245C86" },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className={cx(card, "flex flex-wrap items-center gap-[18px] px-[22px] py-[18px]")}>
        <div className="flex min-w-[280px] flex-1 flex-col gap-[5px]">
          <div className="flex items-center gap-[9px] text-ink">
            {running && <Spinner className="text-blue" />}
            <span className="text-[15px] font-semibold">{running ? "Re-running pre-analysis…" : "Pre-analysis complete"}</span>
          </div>
          <span className="text-[13px] text-muted">Ran when the report was generated · 29 Sep 2026, 14:31 · {ids.length} models · 41 seconds</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {heads.map((m) => (
            <span key={m.id} className="flex items-center gap-[7px] rounded-md bg-sand py-1 pr-2.5 pl-1">
              <Monogram m={m.m} c={m.c} size={22} radius={5} fontSize={10} />
              <span className="text-[13px] font-medium">{m.name}</span>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <Link href="/settings/council" className={cx(btn.outline, "flex h-[38px] items-center px-3.5 text-[13px] text-ink hover:text-ink hover:no-underline")}>
            Configure
          </Link>
          <Button className="h-[38px] px-4 text-[13px]" onClick={run} disabled={running}>Re-run pre-analysis</Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3.5 max-md:grid-cols-1">
        {stats.map((x) => (
          <div key={x.l} className={cx(card, "flex items-center gap-3.5 px-5 py-[18px]")}>
            <span className="font-serif text-[34px] font-semibold" style={{ color: x.c }}>{x.v}</span>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-semibold text-ink">{x.l}</span>
              <span className="text-[12.5px] text-muted">{x.s}</span>
            </div>
          </div>
        ))}
      </div>

      <div className={cx(card, "overflow-hidden")}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-2 px-6 py-4">
          <span className="font-serif text-base font-semibold">Each model&apos;s reading, issue by issue</span>
          <div className="flex gap-3.5 text-[12.5px] text-muted-2">
            <span className="flex items-center gap-1.5"><ReadingTag v="A" className="flex size-[18px] items-center justify-center rounded p-0 text-[10px]" />First reading</span>
            <span className="flex items-center gap-1.5"><ReadingTag v="B" className="flex size-[18px] items-center justify-center rounded p-0 text-[10px]" />Alternative reading</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <div className="grid min-w-[680px] items-center gap-3 border-b border-line-2 bg-panel px-6 py-3" style={{ gridTemplateColumns: cols }}>
            <span className="text-[12.5px] font-medium text-muted">Legal issue and readings</span>
            {heads.map((m) => (
              <span key={m.id} className="justify-self-center">
                <Monogram m={m.m} c={m.c} size={26} radius={6} fontSize={11} title={m.name} />
              </span>
            ))}
            <span className="text-right text-[12.5px] font-medium text-muted">Council</span>
          </div>
          {rows.map((r) => (
            <div key={r.n} className="grid min-w-[680px] items-center gap-3 border-b border-line-4 px-6 py-[18px]" style={{ gridTemplateColumns: cols }}>
              <div className="flex min-w-0 flex-col gap-[7px]">
                <span className="font-serif text-[15.5px] font-semibold text-ink">{r.n}. {r.topic}</span>
                <Reading v="A" text={r.a} />
                {r.b && <Reading v="B" text={r.b} />}
              </div>
              {ids.map((id) => {
                const v = r.votes[id];
                return (
                  <span
                    key={id}
                    className="flex size-[30px] items-center justify-center justify-self-center rounded-[7px] text-[13px] font-semibold"
                    style={{ background: v === "A" ? "#e8f0f7" : "#f7f0e0", color: v === "A" ? "#245C86" : "#8F6A1E" }}
                  >
                    {v}
                  </span>
                );
              })}
              <Badge tone={r.tone} className="justify-self-end px-[9px] py-1 text-xs whitespace-nowrap">{r.cons}</Badge>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
        <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
          <div className="flex items-center gap-2">
            <Dot color="#2E6B4F" />
            <span className="font-serif text-base font-semibold">What the council agrees on</span>
          </div>
          {agree.map((x) => (
            <Point key={x.n} label={`Issue ${x.n} · ${x.topic}`} text={x.majA ? x.a : x.b} />
          ))}
          {FLAGGED.map((x) => (
            <Point key={x.ref} label={`Flagged by every model · ${x.ref}`} text={x.t} />
          ))}
        </div>
        <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
          <div className="flex items-center gap-2">
            <Dot color="#B07A18" />
            <span className="font-serif text-base font-semibold">Where the council divides</span>
          </div>
          {divides.map((x) => (
            <div key={x.n} className="flex flex-col gap-2.5 border-b border-line-4 pb-4">
              <div className="flex justify-between gap-2.5">
                <span className="text-[12.5px] font-medium text-muted">Issue {x.n} · {x.topic}</span>
                <span className="text-xs font-semibold" style={{ color: TONE[x.tone].fg }}>{x.cons}</span>
              </div>
              <Divide v="A" text={x.a} by={x.aBy} color="#245C86" />
              <Divide v="B" text={x.b} by={x.bBy} color="#8F6A1E" />
            </div>
          ))}
          {divides.length === 0 && <span className="text-sm text-muted">The enabled models agree on every issue.</span>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-[10px] bg-sand px-[18px] py-3.5">
        <span className="min-w-[260px] flex-1 text-[13.5px] leading-[1.55] text-body-3">
          The council reads the record and the law. It does not decide the case or predict its outcome; each reading cites the documents and authorities it relies on.
        </span>
        <Link href={`/cases/${caseId}/ask`} className={cx(btn.outline, "flex h-[38px] items-center px-4 text-[13px] font-semibold text-ink hover:text-ink hover:no-underline")}>
          Ask the council a question →
        </Link>
      </div>
    </div>
  );
}

function Reading({ v, text }: { v: "A" | "B"; text: string }) {
  return (
    <div className="flex items-start gap-2">
      <ReadingTag v={v} />
      <span className="text-[13.5px] leading-normal text-body-2">{text}</span>
    </div>
  );
}

function Point({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line-4 pb-3.5">
      <span className="text-[12.5px] font-medium text-muted">{label}</span>
      <span className="font-serif text-[15px] leading-[1.55] text-ink">{text}</span>
    </div>
  );
}

function Divide({ v, text, by, color }: { v: "A" | "B"; text: string; by: string; color: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <ReadingTag v={v} className="mt-0.5" />
      <div className="flex flex-col gap-[3px]">
        <span className="font-serif text-[14.5px] leading-normal text-ink">{text}</span>
        <span className="text-[12.5px]" style={{ color }}>{by}</span>
      </div>
    </div>
  );
}
