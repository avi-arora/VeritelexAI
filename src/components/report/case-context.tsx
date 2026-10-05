"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ACTIVE, api, isStatus, usePoll,
  type ApiCaseDetail, type ReportData, type ReportKey, type RunMode, type RunSummary, type RunView, type StepView,
} from "@/lib/api";
import { useStore } from "@/lib/store";
import { Spinner, card, cx } from "../ui";

type CaseCtx = {
  caseId: string;
  c?: ApiCaseDetail;
  error: Error | null;
  refresh: () => void;
  /** The report version being viewed; null = the published (default) version. */
  selectedRunId: string | null;
  setSelectedRunId: (id: string | null) => void;
  /** Every run (report version) of the case, newest first. Undefined until loaded or when the list cannot be read. */
  runs?: RunSummary[];
  runsError: Error | null;
  refreshRuns: () => void;
};
const Ctx = createContext<CaseCtx | null>(null);

export function CaseProvider({ caseId, children }: { caseId: string; children: ReactNode }) {
  const { data: c, error, refresh } = usePoll(() => api.getCase(caseId), (d) => (d && ACTIVE.includes(d.status) ? 4000 : 30000), [caseId]);
  // Poll the versions while a run is going; otherwise re-read them whenever the case reports a change.
  // `rs` is undefined after a failed fetch: retry slowly (e.g. while the backend restarts).
  const { data: runs, error: runsError, refresh: refreshRuns } = usePoll(
    c ? () => api.runs(caseId) : null,
    (rs) => (!rs ? 15000 : rs.some((r) => r.status === "running") ? 4000 : null),
    [caseId, c?.reportReadyAt, c?.status, c?.latestRunId],
  );
  const [picked, setPicked] = useState<{ caseId: string; runId: string } | null>(null);
  const pickedId = picked?.caseId === caseId ? picked.runId : null;
  // Back to the published version when the picked one disappears, has no report, or is the published one.
  const selectedRunId = pickedId && runs && !runs.some((r) => r.id === pickedId && r.hasReport && !r.published) ? null : pickedId;
  const setSelectedRunId = useCallback(
    (id: string | null) => setPicked(id && !runs?.find((r) => r.id === id)?.published ? { caseId, runId: id } : null),
    [caseId, runs],
  );

  const value = useMemo<CaseCtx>(
    () => ({ caseId, c, error, refresh, selectedRunId, setSelectedRunId, runs, runsError, refreshRuns }),
    [caseId, c, error, refresh, selectedRunId, setSelectedRunId, runs, runsError, refreshRuns],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCase() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCase must be used inside <CaseProvider>");
  return v;
}

/** The case's versions, plus the published one, the one being viewed and whether a run is going. */
export function useRuns() {
  const { c, runs, runsError, refreshRuns, selectedRunId } = useCase();
  const published = runs?.find((r) => r.published);
  const viewed = selectedRunId ? runs?.find((r) => r.id === selectedRunId) : published;
  const active = runs?.find((r) => r.status === "running");
  // The case status also covers the time before the runs list is readable.
  const running = !!active || (!!c && ACTIVE.includes(c.status));
  return { runs, error: runsError, refresh: refreshRuns, published, viewed, active, running };
}

/** Starts a full analysis or a council-only re-run, with toasts for the outcome (a 409 shows the backend's reason). */
export function useStartRun() {
  const { caseId, c, refresh, refreshRuns } = useCase();
  const { showToast } = useStore();
  const [busy, setBusy] = useState(false);
  const caseNo = c?.no;
  const start = useCallback(
    async (mode: RunMode, source?: { id: string; version: number }) => {
      setBusy(true);
      try {
        await api.startRun(caseId, mode === "council" && source ? { mode, sourceRunId: source.id } : { mode });
        showToast(
          mode === "council"
            ? `Council re-run started${source ? ` on version ${source.version}` : ""}`
            : `Analysis re-run started${caseNo ? ` for ${caseNo}` : ""}`,
        );
        refresh();
        refreshRuns();
        return true;
      } catch (e) {
        const what = mode === "council" ? "the council" : "the analysis";
        showToast(isStatus(e, 409) ? (e as Error).message : `Could not start ${what}: ${(e as Error).message}`, "error");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [caseId, caseNo, refresh, refreshRuns, showToast],
  );
  return { start, busy };
}

type Keyed<T> = { key: string; res?: T; err?: Error };

/**
 * A report section of the version being viewed (the published one by default).
 * Re-fetched when the version changes and whenever a newer report is published.
 * Data, error and loading always describe the current version: a previous version's data is never shown.
 */
export function useReport<K extends ReportKey>(section: K): { data?: ReportData[K]; runId?: string; error: Error | null; loading: boolean } {
  type Res = { runId: string; updatedAt: string; data: ReportData[K] };
  const { caseId, c, selectedRunId } = useCase();
  const runId = selectedRunId ?? undefined;
  const key = `${caseId}/${section}/${runId ?? ""}`;
  // Written only by the fetcher (never during render): a failed refresh keeps showing the last good copy.
  const last = useRef<{ key: string; res: Res } | null>(null);
  const { data } = usePoll<Keyed<Res>>(
    async () => {
      try {
        const res = await api.report(caseId, section, runId);
        last.current = { key, res };
        return { key, res };
      } catch (e) {
        // A 404 means the section is not part of this version (e.g. a newly published one): never show the old copy then.
        const keep = last.current?.key === key && !isStatus(e, 404);
        return { key, res: keep ? last.current?.res : undefined, err: e as Error };
      }
    },
    // 404 = the section does not exist for this version; other errors (e.g. 502 while the backend restarts) retry.
    (d) => (d?.err && !isStatus(d.err, 404) ? 10000 : null),
    [key, c?.reportReadyAt],
  );
  const cur = data?.key === key ? data : undefined;
  return { data: cur?.res?.data, runId: cur?.res?.runId, error: cur?.err ?? null, loading: !cur };
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <Spinner /> {label}
    </div>
  );
}

const AGENT_LABEL: Record<string, string> = {
  ingest: "Read document", background: "Background", facts: "Dates & facts", chronology: "Chronology",
  issues: "Legal issues", mapping: "Map to decisions", grounding: "Google Search grounding", verify: "Verify citations", finalize: "Assemble report",
  council: "Council reading", consensus: "Council consensus",
};
const GREY = "#646b73";
const STEP_STATE: Record<string, { label: string; fg: string }> = {
  pending: { label: "Pending", fg: GREY }, queued: { label: "Queued", fg: "#5c646d" }, running: { label: "Running", fg: "#245C86" },
  retrying: { label: "Retrying", fg: "#8F6A1E" }, succeeded: { label: "Done", fg: "#2E6B4F" }, failed: { label: "Failed", fg: "#9B3E35" },
  skipped: { label: "Skipped", fg: GREY }, unavailable: { label: "Not enabled", fg: GREY },
};

/**
 * Label and colour of a step's state. A succeeded step with an `outcome` did not really run: it shows
 * in grey as "Not enabled" (the council member is not enabled in Model Garden) or "Skipped".
 */
export function stepState(s: StepView): { label: string; fg: string; busy: boolean } {
  const st = STEP_STATE[s.status === "succeeded" && s.outcome ? s.outcome : s.status] ?? { label: s.status, fg: GREY };
  return { ...st, busy: s.status === "running" || s.status === "retrying" };
}

/** Renders a report section of the viewed version once available; otherwise shows the live agent run. */
export function ReportGate<K extends ReportKey>({ section, children }: { section: K; children: (data: ReportData[K]) => ReactNode }) {
  const { data, error, loading } = useReport(section);
  const { selectedRunId } = useCase();
  const { viewed } = useRuns();
  if (data) return <>{children(data)}</>;
  if (loading) return <Loading />;
  if (error && !isStatus(error, 404)) return <p className="text-sm text-red">Could not load this section: {error.message}</p>;
  if (selectedRunId) {
    return <div className={cx(card, "px-7 py-6 text-sm text-body-3")}>This section is not part of version {viewed?.version ?? "selected"}.</div>;
  }
  return <RunProgress />;
}

/** "Council reading · Claude Opus 5.5", "Legal issues · 3", "Read document". `nm` names council members. */
export function stepLabel(s: StepView, nm: (id: string) => string) {
  const base = AGENT_LABEL[s.agent] ?? s.agent;
  const sub = s.id.includes("--") ? s.id.split("--")[1] : "";
  if (!sub || s.agent === "ingest" || s.agent === "facts") return base;
  return `${base} · ${s.agent === "council" ? nm(sub) : sub}`;
}

export function RunProgress() {
  const { caseId, c, runs } = useCase();
  const { nm } = useStore();
  const active = !!c && ACTIVE.includes(c.status);
  const { data: run } = usePoll<RunView | undefined>(
    c?.latestRunId ? () => api.latestRun(caseId) : null,
    (r) => (r?.status === "running" ? 3000 : null),
    [caseId, c?.latestRunId, c?.status],
  );
  // Council re-runs reuse the source version's analysis: fold those steps away.
  const fresh = run?.steps.filter((s) => !s.reused) ?? [];
  const reused = run?.steps.filter((s) => s.reused) ?? [];
  const from = run?.sourceRunId ? runs?.find((r) => r.id === run.sourceRunId)?.version : undefined;
  return (
    <div className={cx(card, "flex flex-col gap-4 px-7 py-6")}>
      <div className="flex items-center gap-3">
        {active && <Spinner />}
        <span className="text-[15px] font-semibold text-ink">
          {c?.status === "action" ? "The analysis needs attention" : active ? "The analysis is running" : "This section has not been generated yet"}
        </span>
      </div>
      {c?.note && <p className="m-0 text-sm text-body-3">{c.note}</p>}
      {fresh.length > 0 && <StepGrid steps={fresh} nm={nm} />}
      {reused.length > 0 && (
        <details className="rounded-lg border border-line px-3 py-2">
          <summary className="cursor-pointer text-[13px] text-body-3">
            {reused.length} {reused.length === 1 ? "step" : "steps"} reused from {from ? `version ${from}` : "the earlier version"}
          </summary>
          <div className="pt-2">
            <StepGrid steps={reused} nm={nm} reused />
          </div>
        </details>
      )}
    </div>
  );
}

function StepGrid({ steps, nm, reused }: { steps: StepView[]; nm: (id: string) => string; reused?: boolean }) {
  return (
    <ul role="list" className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-2 p-0">
      {steps.map((s) => {
        const st = reused ? { label: "Reused", fg: GREY, busy: false } : stepState(s);
        return (
          <li key={s.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2" title={s.error ?? undefined}>
            <span className="truncate text-[13px] text-body-2">{stepLabel(s, nm)}</span>
            <span className="flex flex-none items-center gap-1.5 text-xs font-medium" style={{ color: st.fg }}>
              {st.busy && <Spinner />}
              {st.label}
              {s.attempts > 1 ? ` (${s.attempts})` : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function NotYetAvailable() {
  return (
    <div className={cx(card, "px-7 py-6 text-sm text-body-3")}>
      This section is not generated by the analysis pipeline yet. It will be added in a later release.
    </div>
  );
}
