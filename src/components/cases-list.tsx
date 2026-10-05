"use client";

import Link from "next/link";
import { useState } from "react";
import { ACTIVE, api, usePoll, type ApiCaseSummary } from "@/lib/api";
import { STATUS } from "@/lib/data";
import { Chip, Segmented, Spinner, btn, cx } from "./ui";

type Scope = "active" | "past" | "all";
type Group = "all" | "ready" | "progress" | "action";

const SCOPES = [
  { k: "active", label: "Active" },
  { k: "past", label: "Past" },
  { k: "all", label: "All" },
] as const;

const STATUS_TABS: { k: Group; label: string }[] = [
  { k: "all", label: "All" },
  { k: "ready", label: "Report ready" },
  { k: "progress", label: "In progress" },
  { k: "action", label: "Action required" },
];

const COLS = "grid grid-cols-[minmax(0,2.4fr)_minmax(0,1fr)_110px_minmax(0,1.6fr)_120px] gap-5";

type CaseSummary = ApiCaseSummary;

const group = (c: CaseSummary): Exclude<Group, "all"> => (c.status === "ready" ? "ready" : c.status === "action" ? "action" : "progress");

export function CasesList() {
  // Poll quickly while any analysis is running, slowly otherwise.
  const { data, error, loading } = usePoll(api.listCases, (d) => (d?.some((c) => ACTIVE.includes(c.status)) ? 4000 : 30000));
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<Scope>("active");
  const [statusFilter, setStatusFilter] = useState<Group>("all");

  const all: CaseSummary[] = data ?? [];

  const needle = q.trim().toLowerCase();
  const searched = all
    .filter((c) => (scope === "all" ? true : scope === "past" ? !!c.past : !c.past))
    .filter((c) => !needle || `${c.no} ${c.title} ${c.type}`.toLowerCase().includes(needle));
  const rows = searched.filter((c) => statusFilter === "all" || group(c) === statusFilter);
  const count = (g: Group) => searched.filter((c) => g === "all" || group(c) === g).length;

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-7 pt-9 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="mb-2 font-serif text-[30px] leading-[1.2] font-semibold">Cases</h1>
          <p className="m-0 text-[15px] text-muted-2">Every case you have uploaded, with the status of its analysis.</p>
        </div>
        <Link href="/upload" className={cx(btn.primary, "flex h-11 items-center gap-2 px-5 text-sm text-white hover:text-white hover:no-underline")}>
          <span className="text-lg leading-none">+</span>Upload documents
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex h-[46px] min-w-[280px] flex-1 items-center gap-2.5 rounded-lg border border-chip bg-white px-3.5 focus-within:border-blue">
          <span aria-hidden className="size-3.5 flex-none rounded-full border-2 border-muted-3" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by case number, party or subject"
            aria-label="Search cases"
            className="min-w-0 flex-1 border-none bg-transparent text-[15px] text-ink outline-none"
          />
        </label>
        <Segmented options={SCOPES} value={scope} onChange={setScope} />
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((t) => (
          <Chip key={t.k} on={statusFilter === t.k} onClick={() => setStatusFilter(t.k)} className="flex h-[34px] items-center gap-2 rounded-[17px] px-3.5 text-[13px]">
            {t.label}
            <span className="font-mono text-xs font-medium opacity-70">{count(t.k)}</span>
          </Chip>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <div className="min-w-[860px]">
          <div className={cx(COLS, "border-b border-line-2 bg-panel px-6 py-3.5 text-xs font-medium text-muted")}>
            <span>Case</span>
            <span>Division</span>
            <span>Documents</span>
            <span>Analysis status</span>
            <span className="text-right">Updated</span>
          </div>
          {rows.map((c) => (
            <CaseRow key={c.id} c={c} />
          ))}
          {loading && !data && <div className="px-6 py-12 text-center text-sm text-muted">Loading cases…</div>}
          {error && !data && <div className="px-6 py-12 text-center text-sm text-red">Could not load cases: {error.message}</div>}
          {data && all.length === 0 && (
            <div className="px-6 py-12 text-center text-sm text-muted">
              No cases yet. <Link href="/upload">Upload documents</Link> to create the first one.
            </div>
          )}
          {data && all.length > 0 && rows.length === 0 && <div className="px-6 py-12 text-center text-sm text-muted">No cases match this search.</div>}
        </div>
      </div>
    </div>
  );
}

function CaseRow({ c }: { c: CaseSummary }) {
  const st = STATUS[c.status];
  const step = c.status === "action" ? (c.at ?? 0) : st.step;
  const running = c.status === "ingesting" || c.status === "ai";
  const segs = [1, 2, 3, 4].map((i) =>
    c.status === "ready" ? "#2E6B4F"
    : c.status === "action" ? (i < step ? "#9cb8a6" : i === step ? "#C8922E" : "#ebe8e3")
    : i < step ? "#7fa5c4" : i === step ? "#245C86" : "#ebe8e3",
  );
  const label = running && c.pct != null ? `${st.label} · ${c.pct}%` : st.label;
  const cta = c.status === "ready" ? "Open report →" : c.status === "action" ? "Resolve →" : "View progress →";
  const ctaFg = c.status === "ready" ? "#245C86" : c.status === "action" ? "#8F6A1E" : "#9aa0a8";
  // Ready cases open the report; others open the case, which shows live agent progress.
  const href = c.status === "ready" ? `/cases/${c.id}/background` : c.status === "action" ? `/cases/${c.id}/docs` : `/cases/${c.id}/background`;

  const body = (
    <>
      <div className="flex min-w-0 flex-col gap-[5px]">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-mono text-[13px] font-medium text-blue">{c.no}</span>
          {c.isNew && <span className="rounded bg-blue px-[7px] py-0.5 text-[11px] font-semibold text-white">New</span>}
        </div>
        <span className="font-serif text-[15px] leading-[1.4] font-semibold text-ink">{c.title}</span>
        <span className="text-[13px] text-muted">{c.type}</span>
      </div>
      <span className="text-[13px] leading-[1.4] text-body-3">{c.division}</span>
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-ink">{c.docs}</span>
        <span className="text-xs text-muted-3">{c.pages}</span>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-center gap-2" style={{ color: st.fg }}>
          {c.status === "ready" && <StatusDot bg="#2E6B4F">✓</StatusDot>}
          {c.status === "action" && <StatusDot bg="#B07A18">!</StatusDot>}
          {running && <Spinner />}
          {c.status === "queued" && <span className="size-3.5 flex-none rounded-full border-2 border-[#b8b4ad]" />}
          <span className="text-sm font-semibold">{label}</span>
        </div>
        <div className="grid max-w-[240px] grid-cols-4 gap-1">
          {segs.map((bg, i) => (
            <div key={i} className="h-1 rounded-sm" style={{ background: bg }} />
          ))}
        </div>
        <span className="text-[12.5px] leading-[1.45] text-muted-2">{c.note}</span>
      </div>
      <div className="flex flex-col items-end gap-1.5">
        <span className="text-[13px] whitespace-nowrap text-muted-2">{c.updated}</span>
        <span className="text-[13px] font-semibold whitespace-nowrap" style={{ color: ctaFg }}>{cta}</span>
      </div>
    </>
  );

  const rowClass = cx(COLS, "items-center border-b border-line-3 px-6 py-5 text-ink", c.isNew ? "bg-[#f7fafc]" : "bg-white");
  return href ? (
    <Link href={href} className={cx(rowClass, "hover:bg-row-hover hover:text-ink hover:no-underline")}>
      {body}
    </Link>
  ) : (
    <div className={rowClass}>{body}</div>
  );
}

function StatusDot({ bg, children }: { bg: string; children: string }) {
  return (
    <span className="flex size-5 flex-none items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: bg }}>
      {children}
    </span>
  );
}
