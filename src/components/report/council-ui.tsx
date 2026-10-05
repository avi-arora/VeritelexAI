"use client";

import type { ReactNode } from "react";
import { safeHref, type CiteStatus, type CouncilCite, type RunStatus, type RunSummary, type StepState } from "@/lib/api";
import { TONE, type Tone } from "@/lib/data";
import { useStore, type MemberLook } from "@/lib/store";
import { Badge, Button, Monogram, Spinner, card, cx } from "../ui";
import { useRuns, useStartRun } from "./case-context";

/**
 * Model-written text with member mentions ({{m:<memberId>}}, contract §5) rendered as display names
 * through the anonymisation-aware nm(). Output is React text only (no HTML).
 */
export function Mentions({ text }: { text: string }) {
  const { nm } = useStore();
  // With a capture group, split() puts the member ids at the odd indexes.
  const parts = text.split(/\{\{m:([A-Za-z0-9_-]{1,64})\}\}/);
  return <>{parts.map((p, i) => (i % 2 ? <span key={i} className="font-semibold">{nm(p)}</span> : p))}</>;
}

/** External link that only renders http(s) URLs and opens in a new tab without an opener. */
export function ExternalLink({ href, className, children }: { href: string | null | undefined; className?: string; children: ReactNode }) {
  const safe = safeHref(href);
  if (!safe) return null;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

/** A member's monogram (anonymised when the policy says so). Decorative: pair it with the name in text. */
export function MemberMono({ id, fallback, size = 22, dim }: { id: string; fallback?: Partial<MemberLook>; size?: number; dim?: boolean }) {
  const { look } = useStore();
  const l = look(id, fallback);
  return (
    <span aria-hidden className={cx("flex-none", dim && "opacity-45 grayscale")}>
      <Monogram m={l.m} c={l.c} size={size} radius={Math.max(4, Math.round(size / 4.4))} fontSize={Math.round(size * 0.44)} title={l.name} />
    </span>
  );
}

/** Overlapping monograms for "raised by" / "made by", with the names for screen readers. */
export function MemberStack({ ids, size = 20 }: { ids: string[]; size?: number }) {
  const { nm } = useStore();
  return (
    <span className="flex items-center gap-[3px]">
      {ids.map((id) => (
        <MemberMono key={id} id={id} size={size} />
      ))}
      <span className="sr-only">{ids.map((id) => nm(id)).join(", ")}</span>
    </span>
  );
}

export const MEMBER_STATE: Record<StepState, { label: string; tone: Tone }> = {
  pending: { label: "Waiting", tone: "grey" },
  queued: { label: "Waiting", tone: "grey" },
  running: { label: "Reading", tone: "blue" },
  retrying: { label: "Retrying", tone: "amber" },
  succeeded: { label: "Done", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  unavailable: { label: "Not enabled", tone: "grey" },
  skipped: { label: "Skipped", tone: "grey" },
};

/** Member chip with its status in one run; unavailable/failed members are greyed and show the error on hover. */
export function MemberChip({ id, fallback, status, error, showDone }: { id: string; fallback?: Partial<MemberLook>; status: StepState; error?: string | null; showDone?: boolean }) {
  const { look, member } = useStore();
  const st = MEMBER_STATE[status] ?? MEMBER_STATE.pending;
  const busy = status === "running" || status === "retrying";
  const dim = !busy && status !== "succeeded";
  const consoleUrl = status === "unavailable" ? member(id)?.consoleUrl : undefined;
  return (
    <span className={cx("flex items-center gap-[7px] rounded-md bg-sand py-1 pr-2.5 pl-1", dim && "text-muted-2")} title={error ?? undefined}>
      <MemberMono id={id} fallback={fallback} dim={dim} />
      <span className="text-[13px] font-medium">{look(id, fallback).name}</span>
      {(status !== "succeeded" || showDone) && (
        <span className="flex items-center gap-1 text-xs font-medium" style={{ color: TONE[st.tone].fg }}>
          {busy && <Spinner className="size-3 border" />}
          {st.label}
        </span>
      )}
      {consoleUrl && (
        <ExternalLink href={consoleUrl} className="text-xs font-medium">
          Enable in Model Garden
        </ExternalLink>
      )}
    </span>
  );
}

const CITE: Record<CiteStatus, { icon: string; bg: string; label: string; tone: Tone }> = {
  verified: { icon: "✓", bg: "#2E6B4F", label: "verified", tone: "green" },
  warn: { icon: "!", bg: "#B07A18", label: "unverified", tone: "amber" },
  bad: { icon: "×", bg: "#9B3E35", label: "not found", tone: "red" },
};

/** Citations with their verification badge: verified (green), unverified (amber), not found (red). */
export function CiteList({ cites }: { cites: CouncilCite[] }) {
  if (!cites.length) return <span className="text-xs text-muted-3">No citations given.</span>;
  return (
    <ul className="m-0 flex list-none flex-col gap-[9px] p-0">
      {cites.map((ct, i) => {
        const s = CITE[ct.status] ?? CITE.warn;
        return (
          <li key={i} className="flex items-start gap-[9px]">
            <span aria-hidden className="mt-px flex size-[18px] flex-none items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: s.bg }}>
              {s.icon}
            </span>
            <div className="flex min-w-0 flex-col gap-[3px]">
              <span className="text-[13px] leading-[1.4] font-medium break-words text-ink">{ct.text}</span>
              <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <Badge tone={s.tone} className="rounded px-1.5 py-px text-[11px]">{s.label}</Badge>
                <span>{ct.kind === "record" ? "Case record" : "Authority"}</span>
              </span>
              {ct.note && (
                <span className="line-clamp-4 border-l-2 border-line pl-2 text-xs leading-[1.5] break-words whitespace-pre-line text-body-3">{ct.note}</span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export const RUN_STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  running: { label: "Running", tone: "blue" },
  succeeded: { label: "Completed", tone: "green" },
  partial: { label: "Completed with gaps", tone: "amber" },
  failed: { label: "Failed", tone: "red" },
};

/** Why a run exists: "Documents uploaded", "Full re-run" or "Council re-run of version N". */
export function runTriggerLabel(r: RunSummary) {
  if (r.mode === "council" || r.trigger === "council") return `Council re-run of version ${r.sourceVersion ?? "?"}`;
  return r.trigger === "upload" ? "Documents uploaded" : "Full re-run";
}

/** Shown when the viewed version has no council section (versions made before the council existed). */
export function CouncilNotRun({ what }: { what: "council" | "questions" }) {
  const { viewed, running, active } = useRuns();
  const { start, busy } = useStartRun();
  const label = viewed ? `version ${viewed.version}` : "this version";
  return (
    <div className={cx(card, "flex flex-col gap-3.5 px-7 py-6")}>
      <div className="flex items-center gap-2.5">
        {active?.mode === "council" && <Spinner className="text-blue" />}
        <span className="text-[15px] font-semibold text-ink">
          {active?.mode === "council" ? "Council re-run in progress…" : `The council was not run for ${label}`}
        </span>
      </div>
      <p className="m-0 max-w-[720px] text-sm leading-[1.6] text-body-3">
        {what === "council"
          ? "Versions made before the model council was added have no council reading. "
          : "Questions for counsel come from the council's reading of the record, and there is none for this version. "}
        Running the council reuses the analysis of {label} and saves the result as a new version.
      </p>
      {active?.mode === "council" && active.council.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {active.council.map((m) => (
            <MemberChip key={m.id} id={m.id} status={m.status} error={m.error} showDone />
          ))}
        </div>
      )}
      <div>
        <Button className="h-[38px] px-4 text-[13px]" disabled={busy || running} onClick={() => start("council", viewed)}>
          Run the council on this version
        </Button>
      </div>
    </div>
  );
}
