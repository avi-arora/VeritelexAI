"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { BACKGROUND, DOCS, GAPS, ISSUES, KEY_FACTS, MAPPING, MATRIX, SUBS, TOTAL_DECISIONS } from "@/lib/data";
import { Badge, DashList, Dot, btn, card, cx } from "../ui";

function useBase() {
  const { caseId } = useParams<{ caseId: string }>();
  return `/cases/${caseId}`;
}

export function Background() {
  const base = useBase();
  const jump = [
    { v: MATRIX.length, l: "Dated facts", k: "matrix" },
    { v: TOTAL_DECISIONS, l: "Decisions and orders mapped", k: "mapping" },
    { v: ISSUES.length, l: "Legal issues", k: "issues" },
    { v: GAPS.length, l: "Points the research tools missed", k: "gaps" },
  ];
  return (
    <div className="flex flex-col gap-6">
      <div className={cx(card, "flex flex-col gap-4 px-8 py-7")}>
        {BACKGROUND.map((p) => (
          <p key={p} className="text-pretty m-0 font-serif text-[16.5px] leading-[1.75] text-prose">{p}</p>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line max-md:grid-cols-1">
        {KEY_FACTS.map((k) => (
          <div key={k.k} className="bg-white px-5 py-[18px]">
            <span className="mb-1.5 block text-[12.5px] font-medium text-muted">{k.k}</span>
            <span className="text-[14.5px] leading-[1.45] font-medium text-ink">{k.v}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-4 gap-3.5 max-md:grid-cols-2">
        {jump.map((j) => (
          <Link key={j.k} href={`${base}/${j.k}`} className={cx(card, "flex flex-col gap-1.5 px-5 py-[18px] hover:border-blue hover:no-underline")}>
            <span className="font-serif text-[28px] font-semibold text-ink">{j.v}</span>
            <span className="text-sm font-medium text-body-2">{j.l}</span>
            <span className="mt-1 text-[13px] font-medium text-blue">View →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function Mapping() {
  return (
    <div className="flex flex-col gap-[18px]">
      {MAPPING.map((g) => (
        <div key={g.t} className={cx(card, "overflow-hidden")}>
          <div className="flex flex-wrap items-baseline gap-4 border-b border-line-2 bg-panel px-6 py-4">
            <span className="font-mono text-[13.5px] font-medium text-ink">{g.d}</span>
            <span className="font-serif text-base font-semibold text-ink">{g.t}</span>
            <span className="ml-auto text-[13px] text-muted">{g.iss}</span>
          </div>
          {g.decisions.map((x) => (
            <div key={x.name} className="grid grid-cols-[minmax(0,1.5fr)_150px_minmax(0,1.3fr)] items-start gap-5 border-b border-line-4 px-6 py-[18px] max-md:grid-cols-1">
              <div className="flex min-w-0 flex-col gap-[5px]">
                <a href={x.href} target="_blank" rel="noopener noreferrer" className="font-serif text-base leading-[1.4] text-blue-dark italic">
                  {x.name} ↗
                </a>
                <span className="font-mono text-[13px] text-muted-2">{x.cite}</span>
                <span className="text-[12.5px] text-muted-3">{x.court} · via {x.via}</span>
              </div>
              <div className="flex flex-col items-start gap-[7px]">
                <span className="text-xs text-muted">Date of decision</span>
                <span className="text-sm font-medium text-ink">{x.date}</span>
                <Badge tone={x.tone} className="px-[9px] py-[3px] text-xs">{x.rel}</Badge>
              </div>
              <div className="flex flex-col gap-[5px]">
                <span className="text-xs text-muted">How it relates</span>
                <span className="text-sm leading-[1.6] text-body-2">{x.how}</span>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function Issues() {
  const base = useBase();
  return (
    <div className="flex flex-col gap-3.5">
      {ISSUES.map((i) => {
        const facts = MATRIX.filter((m) => m.iss.includes(i.n)).map((m) => m.d).join(" · ") || "—";
        return (
          <div key={i.n} className={cx(card, "grid grid-cols-[84px_minmax(0,1fr)_auto] items-start gap-5 px-[26px] py-[22px] max-sm:grid-cols-1")}>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-3">Issue</span>
              <span className="font-serif text-[26px] font-semibold text-blue">{i.n}</span>
            </div>
            <div className="flex min-w-0 flex-col gap-2.5">
              <span className="text-[13px] font-medium text-muted">{i.topic}</span>
              <p className="text-pretty m-0 font-serif text-[17px] leading-[1.55] text-ink">{i.q}</p>
              <div className="flex flex-wrap gap-[18px] text-[13px] text-muted-2">
                <span>{i.law}</span>
                <span>Facts: {facts}</span>
              </div>
            </div>
            <div className="flex flex-col items-end gap-2.5 max-sm:items-start">
              <Badge tone={i.tone} className="px-2.5 py-1 text-[12.5px] whitespace-nowrap">{i.st}</Badge>
              <Link href={`${base}/subs?issue=${i.n}`} className="text-[13px] font-medium whitespace-nowrap">Submissions →</Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Submissions() {
  const base = useBase();
  const param = Number(useSearchParams().get("issue"));
  const issue = ISSUES.find((i) => i.n === param) ?? ISSUES[2];
  const sub = SUBS[issue.n];
  return (
    <div className="flex flex-col gap-[18px]">
      <div className="flex flex-wrap gap-2" role="tablist">
        {ISSUES.map((i) => {
          const on = i.n === issue.n;
          return (
            <Link
              key={i.n}
              href={`${base}/subs?issue=${i.n}`}
              replace
              scroll={false}
              role="tab"
              aria-selected={on}
              className={cx(
                "flex h-9 items-center rounded-[18px] border px-3.5 text-[13px] font-medium hover:no-underline",
                on ? "border-navy bg-navy text-white hover:text-white" : "border-chip bg-white text-body-2 hover:text-ink",
              )}
            >
              {i.n}. {i.topic}
            </Link>
          );
        })}
      </div>
      <div className={cx(card, "overflow-hidden")}>
        <div className="border-b border-line-2 px-[26px] py-[22px]">
          <span className="text-[13px] font-medium text-muted">Issue {issue.n} · {issue.topic}</span>
          <p className="mt-2 mb-0 font-serif text-lg leading-normal text-ink">{issue.q}</p>
        </div>
        <div className="grid grid-cols-2 max-md:grid-cols-1">
          <PartyColumn party="Claimant" name="Meridian Gulf" color="#245C86" points={sub.c} cite={sub.cRef} className="border-r border-line-2 max-md:border-r-0 max-md:border-b" />
          <PartyColumn party="Defendant" name="Aurora Vertex" color="#8a8378" points={sub.d} cite={sub.dRef} />
        </div>
        <div className="flex items-baseline gap-2.5 border-t border-line-2 bg-panel px-[26px] py-4">
          <span className="text-[13px] font-semibold text-body-2">Where it stands</span>
          <span className="text-sm text-body-3">{sub.pos}</span>
        </div>
      </div>
    </div>
  );
}

function PartyColumn({ party, name, color, points, cite, className }: { party: string; name: string; color: string; points: string[]; cite: string; className?: string }) {
  return (
    <div className={cx("flex flex-col gap-3.5 px-[26px] py-6", className)}>
      <div className="flex items-center gap-2">
        <Dot color={color} square />
        <span className="text-sm font-semibold">{party}</span>
        <span className="text-[13px] text-muted">{name}</span>
      </div>
      <DashList items={points} />
      <span className="text-[13px] text-blue">{cite}</span>
    </div>
  );
}

export function Gaps() {
  return (
    <div className="flex flex-col gap-3.5">
      {GAPS.map((g) => (
        <div key={g.t} className={cx(card, "grid grid-cols-[minmax(0,1fr)_210px] items-start gap-6 px-[26px] py-[22px] max-md:grid-cols-1")}>
          <div className="flex flex-col items-start gap-2">
            <Badge tone={g.tone} className="px-[9px] py-[3px] text-xs">{g.kind}</Badge>
            <span className="font-serif text-[17px] leading-[1.4] font-semibold text-ink">{g.t}</span>
            <p className="text-pretty m-0 text-[14.5px] leading-[1.65] text-body-3">{g.b}</p>
          </div>
          <div className="flex flex-col gap-3 border-l border-line-3 pl-5">
            <div>
              <span className="mb-[3px] block text-xs text-muted">Found via</span>
              <span className="text-[13.5px] font-medium text-ink">{g.via}</span>
            </div>
            <div>
              <span className="mb-[3px] block text-xs text-muted">Bears on</span>
              <span className="text-[13.5px] font-medium text-blue">{g.ref}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Documents() {
  return (
    <div className={cx(card, "overflow-hidden")}>
      {DOCS.map((d) => (
        <div key={d.n} className="grid grid-cols-[minmax(0,1fr)_100px_130px_150px] items-center gap-4 border-b border-line-4 px-6 py-4 max-md:grid-cols-[minmax(0,1fr)_auto]">
          <span className="text-[14.5px] font-medium text-ink">{d.n}</span>
          <span className="text-[13px] text-muted max-md:hidden">{d.p}</span>
          <span className="text-[13px] text-muted-2 max-md:hidden">{d.by}</span>
          <Badge tone={d.tone} className="justify-self-end px-[9px] py-1 text-xs">{d.s}</Badge>
        </div>
      ))}
      <div className="flex justify-end px-6 py-4">
        <Link href="/upload" className={cx(btn.primary, "flex h-10 items-center px-4 text-[13.5px] text-white hover:text-white hover:no-underline")}>
          Add documents
        </Link>
      </div>
    </div>
  );
}
