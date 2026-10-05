"use client";

import Link from "next/link";
import type { RunSummary } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { DropPanel } from "../popover";
import { Badge, btn, cx } from "../ui";
import { useCase, useRuns } from "./case-context";
import { runTriggerLabel } from "./council-ui";

const when = (r: RunSummary) => r.finishedAt ?? r.createdAt;

/** "Current" for the published version, "Earlier version" for older ones. */
function standing(r: RunSummary, published?: RunSummary) {
  if (r.published) return "Current";
  return published && r.version > published.version ? "Not published" : "Earlier version";
}

/** Compact "Version N · date · Current" control; its panel lists every version that has a report, newest first. */
export function VersionSwitcher() {
  const { caseId, setSelectedRunId } = useCase();
  const { runs, published, viewed } = useRuns();
  const list = (runs ?? []).filter((r) => r.hasReport);
  if (!viewed || !list.length) return null;
  const summary = `Version ${viewed.version} · ${fmtDate(when(viewed))} · ${standing(viewed, published)}${viewed.status === "partial" ? " · with gaps" : ""}`;

  return (
    <DropPanel
      triggerLabel={`${summary}. Change the version shown`}
      triggerClassName="flex h-[30px] items-center gap-2 rounded-md border border-field bg-white px-2.5 text-[12.5px] font-medium text-body-2 hover:border-blue"
      trigger={
        <>
          <span>{summary}</span>
          <span aria-hidden className="text-[10px] text-muted">
            ▼
          </span>
        </>
      }
    >
      <div className="flex flex-col py-1.5">
        <span className="px-3.5 pt-1 pb-1.5 text-[11.5px] font-medium tracking-[.06em] text-muted-3 uppercase">Report versions</span>
        <ul role="list" className="m-0 flex list-none flex-col p-0">
          {list.map((r) => {
            const on = r.id === viewed.id;
            return (
              <li key={r.id}>
                <button
                  type="button"
                  aria-current={on ? "true" : undefined}
                  onClick={() => setSelectedRunId(r.published ? null : r.id)}
                  className={cx(
                    "flex w-full flex-col items-start gap-0.5 px-3.5 py-2 text-left hover:bg-row-hover focus-visible:bg-row-hover",
                    on && "bg-blue-tint/70",
                  )}
                >
                  <span className="flex items-center gap-2 text-[13.5px] font-semibold text-ink">
                    Version {r.version}
                    {r.published && <Badge tone="green">Current</Badge>}
                    {on && <span className="text-xs font-medium text-blue">Viewing</span>}
                  </span>
                  <span className="text-xs leading-[1.45] text-muted">
                    {fmtDateTime(when(r))} · {runTriggerLabel(r)}
                    {r.status === "partial" ? " · Completed with gaps" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="mx-3.5 mt-1.5 border-t border-line pt-2 pb-1">
          <Link href={`/cases/${caseId}/versions`} className="text-[13px] font-medium">
            All versions and runs →
          </Link>
        </div>
      </div>
    </DropPanel>
  );
}

/** Slim banner under the header while an earlier version is shown. */
export function VersionBanner() {
  const { selectedRunId, setSelectedRunId } = useCase();
  const { viewed, published } = useRuns();
  if (!selectedRunId || !viewed) return null;
  return (
    <div className="border-b border-[#ecdcb4] bg-[#fbf5e6]">
      <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-7 py-2.5">
        <p className="m-0 text-[13.5px] leading-[1.5] text-[#5f4813]">
          You are viewing version {viewed.version} ({fmtDate(when(viewed))}).
          {published ? ` The current version is ${published.version}.` : ""}
        </p>
        <button type="button" onClick={() => setSelectedRunId(null)} className={cx(btn.outline, "h-8 px-3 text-[13px]")}>
          Back to current version
        </button>
      </div>
    </div>
  );
}
