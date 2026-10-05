"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, isStatus, type RunSummary, type RunView } from "@/lib/api";
import { fmtDateTime, fmtDuration, secondsBetween } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Badge, Button, card, cx } from "../ui";
import { Loading, stepLabel, stepState, useCase, useRuns, useStartRun } from "./case-context";
import { MemberChip, RUN_STATUS, runTriggerLabel } from "./council-ui";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

// The backend reports a run's stage as a code: "queued" | "ingesting" | "ai" | "done".
const STAGE_LABEL: Record<string, string> = { queued: "Waiting to start", ingesting: "Reading the documents", ai: "AI analysis" };
const stageLabel = (r: RunSummary) => (r.stage === "ai" && r.mode === "council" ? "The council is reading the record" : STAGE_LABEL[r.stage] ?? "");

/** "Analysis versions": every run of the case, newest first, with the actions that apply to each. */
export function Versions() {
  const { runs, error, running } = useRuns();
  const { start, busy } = useStartRun();

  let body;
  if (runs) {
    body = runs.length ? (
      <ul role="list" className="m-0 flex list-none flex-col gap-3 p-0">
        {runs.map((r) => (
          <VersionRow key={r.id} r={r} newest={r.id === runs[0].id} />
        ))}
      </ul>
    ) : (
      <div className={cx(card, "px-7 py-6 text-sm text-body-3")}>No analysis has been run for this case yet.</div>
    );
  } else if (error) {
    body = (
      <div className={cx(card, "px-7 py-6 text-sm text-body-3")}>
        {isStatus(error, 404) ? "The list of versions is not available yet. Try again in a few minutes." : `Could not load the versions: ${error.message}`}
      </div>
    );
  } else {
    body = <Loading label="Loading versions…" />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 max-w-[640px] text-sm leading-[1.6] text-body-3">
          The current version is the newest one that finished with a report. Earlier versions stay readable.
        </p>
        <Button className="h-10 px-4 text-[13.5px]" disabled={busy || running} onClick={() => start("full")}>
          Run a new analysis
        </Button>
      </div>
      {body}
    </div>
  );
}

function VersionRow({ r, newest }: { r: RunSummary; newest: boolean }) {
  const router = useRouter();
  const { caseId, c, selectedRunId, setSelectedRunId } = useCase();
  const { running } = useRuns();
  const { start, busy } = useStartRun();
  const st = RUN_STATUS[r.status] ?? RUN_STATUS.failed;
  const viewing = selectedRunId ? selectedRunId === r.id : r.published;
  const took = fmtDuration(secondsBetween(r.createdAt, r.finishedAt));
  const counts = r.counts ? [plural(r.counts.facts, "fact"), plural(r.counts.issues, "issue"), plural(r.counts.decisions, "decision")] : [];

  const view = () => {
    setSelectedRunId(r.published ? null : r.id);
    router.push(`/cases/${caseId}/background`);
  };

  return (
    <li className={cx(card, "flex flex-col gap-3 px-6 py-5", viewing && "border-[#bcd2e4] shadow-[0_0_0_1px_#bcd2e4]")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="m-0 font-serif text-[19px] font-semibold text-ink">Version {r.version}</h3>
            {r.published && <Badge tone="green">Current</Badge>}
            {viewing && <Badge tone="blue">Viewing</Badge>}
          </div>
          <span className="text-[13px] text-muted">
            {runTriggerLabel(r)} · started {fmtDateTime(r.createdAt)}
            {took ? ` · took ${took}` : ""}
          </span>
        </div>
        <Badge tone={st.tone}>{r.status === "running" ? `Running · ${Math.round(r.pct)}%` : st.label}</Badge>
      </div>

      {r.status === "running" && (
        <div className="flex flex-wrap items-center gap-3">
          <progress
            value={Math.max(0, Math.min(100, r.pct))}
            max={100}
            aria-label={`Version ${r.version} progress`}
            className="h-1.5 w-48 appearance-none overflow-hidden rounded-full bg-line [&::-moz-progress-bar]:bg-blue [&::-webkit-progress-bar]:bg-line [&::-webkit-progress-value]:bg-blue"
          />
          {stageLabel(r) && <span className="text-[13px] text-body-3">{stageLabel(r)}</span>}
        </div>
      )}

      {(counts.length > 0 || r.docCount > 0) && (
        <p className="m-0 text-[13.5px] text-body-2">{[...counts, plural(r.docCount, "document")].join(" · ")}</p>
      )}

      {r.council.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Council</span>
          {r.council.map((m) => (
            <MemberChip key={m.id} id={m.id} status={m.status} error={m.error} />
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2.5">
        <Button variant="outline" className="h-9 px-3.5 text-[13px] disabled:cursor-not-allowed disabled:opacity-50" disabled={!r.hasReport} onClick={view}>
          View
        </Button>
        {r.hasReport && (
          <Button variant="outline" className="h-9 px-3.5 text-[13px] disabled:cursor-not-allowed disabled:opacity-50" disabled={busy || running} onClick={() => start("council", r)}>
            Re-run council on this version
          </Button>
        )}
        {r.status === "failed" && (c?.latestRunId ? c.latestRunId === r.id : newest) && <ResumeButton runId={r.id} />}
      </div>

      {r.status !== "running" && <RunSteps r={r} />}
    </li>
  );
}

function ResumeButton({ runId }: { runId: string }) {
  const { caseId, c, refresh } = useCase();
  const { running, refresh: refreshRuns } = useRuns();
  const { showToast } = useStore();
  const [busy, setBusy] = useState(false);
  const resume = async () => {
    setBusy(true);
    try {
      await api.resumeRun(caseId, runId);
      showToast(`Resuming the analysis${c ? ` for ${c.no}` : ""}`);
      refresh();
      refreshRuns();
    } catch (e) {
      showToast(isStatus(e, 409) ? (e as Error).message : `Could not resume the analysis: ${(e as Error).message}`, "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button className="h-9 px-3.5 text-[13px]" disabled={busy || running} onClick={resume}>
      Resume
    </Button>
  );
}

/** On expand, read the run: list the steps that did not simply succeed, and count the completed and reused ones. */
function RunSteps({ r }: { r: RunSummary }) {
  const { caseId } = useCase();
  const { nm } = useStore();
  const [state, setState] = useState<{ view?: RunView; error?: Error; loading?: boolean }>({});

  const load = async () => {
    setState({ loading: true });
    try {
      setState({ view: await api.getRun(caseId, r.id) });
    } catch (e) {
      setState({ error: e as Error });
    }
  };
  const steps = state.view?.steps ?? [];
  const reused = steps.filter((s) => s.reused).length;
  // Failed, not run, not enabled, skipped, or retried with an error. Plain successes are only counted.
  const notable = steps.filter((s) => !s.reused && (s.status !== "succeeded" || !!s.outcome || !!s.error));
  const done = steps.length - reused - notable.length;
  const tally = [
    done ? `${plural(done, "step")} completed` : "",
    reused ? `${plural(reused, "step")} reused from version ${r.sourceVersion ?? "?"}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <details
      className="group rounded-lg border border-line bg-panel px-4 py-2.5"
      onToggle={(e) => {
        if (e.currentTarget.open && !state.view && !state.loading) void load();
      }}
    >
      <summary className="cursor-pointer text-[13px] font-medium text-body-2">
        {r.status === "failed" ? "What went wrong" : r.status === "partial" ? "What is missing from this version" : "Steps of this run"}
      </summary>
      <div className="flex flex-col gap-2.5 pt-2.5">
        {state.loading && <Loading label="Reading the run…" />}
        {state.error && <p className="m-0 text-[13px] text-red">Could not read this run: {state.error.message}</p>}
        {notable.length > 0 && (
          <ul role="list" className="m-0 flex list-none flex-col gap-2 p-0">
            {notable.map((s) => {
              const st = stepState(s);
              const notRun = s.status === "pending" || s.status === "queued";
              return (
                <li key={s.id} className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-semibold text-ink">
                    {stepLabel(s, nm)}
                    <span className="font-medium" style={{ color: st.fg }}>
                      {` · ${notRun ? "Not run" : st.label}${s.attempts > 1 ? ` after ${s.attempts} attempts` : ""}`}
                    </span>
                  </span>
                  {s.error && (
                    <span className={cx("text-[13px] leading-[1.5] break-words", s.status === "failed" ? "text-red" : "text-body-3")}>{s.error}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {state.view && (tally || !notable.length) && <p className="m-0 text-[13px] text-body-3">{tally || "No steps were recorded for this run."}</p>}
      </div>
    </details>
  );
}
