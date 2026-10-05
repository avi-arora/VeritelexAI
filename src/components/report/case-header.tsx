"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { STATUS } from "@/lib/data";
import { fmtDate } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Button, Spinner, btn, cx } from "../ui";
import { useCase, useRuns, useStartRun } from "./case-context";
import { VersionBanner, VersionSwitcher } from "./version-switcher";

export function CaseHeader() {
  const { showToast, setExportOpen } = useStore();
  const { caseId, c, error, refresh } = useCase();
  const { viewed, running, refresh: refreshRuns } = useRuns();
  const { start, busy: starting } = useStartRun();
  const [resuming, setResuming] = useState(false);

  // Resume from checkpoints: only failed work is redone.
  const resume = async () => {
    if (!c?.latestRunId) return;
    setResuming(true);
    try {
      await api.resumeRun(caseId, c.latestRunId);
      showToast(`Resuming the analysis for ${c.no}`);
      refresh();
      refreshRuns();
    } catch (e) {
      showToast(`Could not resume the analysis: ${(e as Error).message}`, "error");
    } finally {
      setResuming(false);
    }
  };

  const busy = starting || resuming;
  const canResume = c?.status === "action" && !!c.latestRunId;
  // The council re-run reuses the analysis of the version being viewed (the published one by default).
  const councilSource = viewed?.hasReport ? viewed : undefined;
  const canRunCouncil = !!councilSource || !!c?.reportReadyAt;

  return (
    <>
      <div className="border-b border-line bg-white">
        <div className="mx-auto max-w-[1320px] px-7 pt-[22px] pb-6">
          <Link href="/cases" className="mb-3 inline-block text-[13px] font-medium">← All cases</Link>
          {error && !c && <p className="m-0 text-sm text-red">Could not load the case: {error.message}</p>}
          {c && (
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-3">
                  <span className="font-mono text-sm font-medium text-blue">{c.no}</span>
                  {c.status === "ready" ? (
                    <span className="flex items-center gap-1.5 rounded-[5px] bg-[#e7f0ea] px-2.5 py-1 text-[12.5px] font-semibold text-green">
                      <span>✓</span>Report ready · {fmtDate(c.reportReadyAt)}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 rounded-[5px] bg-panel px-2.5 py-1 text-[12.5px] font-semibold" style={{ color: STATUS[c.status].fg }}>
                      {running && <Spinner />}
                      {STATUS[c.status].label}
                      {running && c.pct != null ? ` · ${c.pct}%` : ""}
                    </span>
                  )}
                  <VersionSwitcher />
                </div>
                <h1 className="text-pretty mb-2 font-serif text-[26px] leading-[1.3] font-semibold">{c.title}</h1>
                <span className="text-sm text-muted-2">{c.subtitle || c.type}</span>
              </div>
              <div className="flex flex-wrap gap-2.5">
                <Link href="/upload" className={cx(btn.outline, "flex h-10 items-center px-4 text-[13.5px] text-ink hover:text-ink hover:no-underline")}>
                  Add documents
                </Link>
                {canRunCouncil && (
                  <Button
                    variant="outline"
                    className="h-10 px-4 text-[13.5px] disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => start("council", councilSource)}
                    disabled={busy || running}
                    title={councilSource && !councilSource.published ? `Re-runs the council on version ${councilSource.version}` : undefined}
                  >
                    Re-run council only
                  </Button>
                )}
                <Button
                  variant="outline"
                  className="h-10 px-4 text-[13.5px] disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={canResume ? resume : () => start("full")}
                  disabled={busy || running}
                >
                  {canResume ? "Resume analysis" : "Re-run analysis"}
                </Button>
                <Button className="h-10 px-[18px] text-[13.5px]" onClick={() => setExportOpen(true)} disabled={c.status !== "ready"}>
                  Export / print
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
      <VersionBanner />
    </>
  );
}
