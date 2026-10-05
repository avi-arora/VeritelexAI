"use client";

import Link from "next/link";
import { isStatus, type CouncilData } from "@/lib/api";
import { TONE } from "@/lib/data";
import { fmtDateTime, fmtDuration } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Button, Dot, ReadingTag, Spinner, btn, card, cx } from "../ui";
import { Loading, RunProgress, useCase, useReport, useRuns, useStartRun } from "./case-context";
import { CouncilNotRun, MemberChip, MemberStack } from "./council-ui";
import { ReadingsOnly, VotesTable, consensus } from "./council-votes";

/** Council pre-analysis of the version being viewed: votes, readings, agreement, division and flagged facts. */
export function CouncilPreAnalysis() {
  const { c } = useCase();
  const { published } = useRuns();
  const { data, error, loading } = useReport("council");
  if (data) return <CouncilView data={data} />;
  if (loading) return <Loading />;
  if (error && !isStatus(error, 404)) return <p className="text-sm text-red">Could not load the council pre-analysis: {error.message}</p>;
  // 404: no report at all yet (show the run), or a version made before the council existed.
  if (!c?.reportReadyAt && !published) return <RunProgress />;
  return <CouncilNotRun what="council" />;
}

function CouncilView({ data }: { data: CouncilData }) {
  const { caseId } = useCase();
  const { viewed, running, active } = useRuns();
  const { start, busy } = useStartRun();
  const { isOn, nm, anon } = useStore();

  // Columns: members that answered in this run and are switched on in Settings.
  const answered = data.members.filter((m) => m.status === "succeeded");
  const ids = answered.filter((m) => isOn(m.id)).map((m) => m.id);
  const hidden = answered.filter((m) => !isOn(m.id));
  // Agreement needs at least two readings side by side.
  const comparable = data.compared && ids.length > 1;
  const rows = data.rows.map((r) => ({ r, cons: consensus(r, ids) }));
  const agree = rows.filter((x) => x.cons.unanimous);
  const divides = rows.filter((x) => x.cons.divided);
  const rerunning = active?.mode === "council";
  const took = fmtDuration(data.durationS);
  const count = answered.length === data.members.length ? `${data.members.length} models` : `${answered.length} of ${data.members.length} models answered`;
  // The backend's note names the models, so rebuild it from the member list while anonymised.
  const note = anon
    ? data.members
        .filter((m) => m.status !== "succeeded")
        .map((m) => `${nm(m.id, m.name)} ${m.status === "unavailable" ? "was not enabled in Model Garden" : "did not answer"}.`)
        .join(" ")
    : data.note;
  // Facts flagged by models that are switched off are hidden, like their readings.
  const flagged = data.flagged
    .map((f) => ({ ...f, shownBy: f.by.filter((id) => ids.includes(id)) }))
    .filter((f) => !f.by.length || f.shownBy.length);

  const stats = [
    { v: agree.length, l: "Issues agreed", s: "every model shown reads it the same way", c: "#2E6B4F" },
    { v: divides.length, l: "Issues where it divides", s: "majority or split", c: "#B07A18" },
    { v: flagged.length, l: "Facts flagged", s: "decisive points in the record", c: "#245C86" },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className={cx(card, "flex flex-wrap items-center gap-[18px] px-[22px] py-[18px]")}>
        <div className="flex min-w-[280px] flex-1 flex-col gap-[5px]">
          <div className="flex items-center gap-[9px] text-ink">
            {rerunning && <Spinner className="text-blue" />}
            <span className="text-[15px] font-semibold">{rerunning ? "Council re-run in progress…" : "Pre-analysis complete"}</span>
          </div>
          <span className="text-[13px] text-muted">
            {[viewed ? `Version ${viewed.version}` : "", fmtDateTime(data.ranAt), count, took].filter(Boolean).join(" · ")}
          </span>
          {data.chair && (
            <span className="text-[13px] text-muted">
              Consensus drawn up by {nm(data.chair.id)}
              {!anon && data.chair.model ? ` (${data.chair.model})` : ""}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.members.map((m) => (
            <MemberChip key={m.id} id={m.id} fallback={{ name: m.name, m: m.m, c: m.c }} status={m.status} error={m.error} />
          ))}
        </div>
        <div className="flex gap-2">
          <Link href="/settings/council" className={cx(btn.outline, "flex h-[38px] items-center px-3.5 text-[13px] text-ink hover:text-ink hover:no-underline")}>
            Configure
          </Link>
          <Button className="h-[38px] px-4 text-[13px]" onClick={() => start("council", viewed)} disabled={busy || running}>
            Re-run council
          </Button>
        </div>
      </div>

      {note && (
        <p className="m-0 rounded-[10px] border border-[#ecdcb4] bg-[#fbf5e6] px-[18px] py-3 text-[13.5px] leading-[1.55] text-[#5f4813]">{note}</p>
      )}
      {hidden.length > 0 && (
        <p className="m-0 text-[13px] text-muted">
          Not shown: {hidden.map((m) => nm(m.id, m.name)).join(", ")} (switched off in <Link href="/settings/council">Settings</Link>).
        </p>
      )}

      {!comparable && (
        <div className={cx(card, "px-6 py-5 text-sm leading-[1.6] text-body-3")}>
          {!answered.length
            ? "No model answered in this run."
            : !ids.length
              ? "No model that answered is switched on. Switch members on in Settings to see their readings."
              : !data.compared
                ? "The readings could not be compared automatically, so each model’s own reading is shown below."
                : `Only ${nm(ids[0])} ${hidden.length ? "is shown" : "answered"}, so there is nothing to compare. Its reading of each issue is below.`}
        </div>
      )}

      {comparable ? (
        <>
          <div className="grid grid-cols-3 gap-3.5 max-md:grid-cols-1">
            {stats.map((x) => (
              <div key={x.l} className={cx(card, "flex items-center gap-3.5 px-5 py-[18px]")}>
                <span className="font-serif text-[34px] font-semibold" style={{ color: x.c }}>
                  {x.v}
                </span>
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-semibold text-ink">{x.l}</span>
                  <span className="text-[12.5px] text-muted">{x.s}</span>
                </div>
              </div>
            ))}
          </div>

          <VotesTable data={data} ids={ids} />

          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
              <div className="flex items-center gap-2">
                <Dot color="#2E6B4F" />
                <h3 className="m-0 font-serif text-base font-semibold">What the council agrees on</h3>
              </div>
              {agree.map(({ r, cons }) => (
                <Point key={r.n} label={`Issue ${r.n} · ${r.topic}`} text={cons.agreed === "B" ? r.b : r.a} />
              ))}
              {agree.length === 0 && <span className="text-sm text-muted">The models shown agree on no issue.</span>}
            </div>
            <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
              <div className="flex items-center gap-2">
                <Dot color="#B07A18" />
                <h3 className="m-0 font-serif text-base font-semibold">Where the council divides</h3>
              </div>
              {divides.map(({ r, cons }) => (
                <div key={r.n} className="flex flex-col gap-2.5 border-b border-line-4 pb-4">
                  <div className="flex justify-between gap-2.5">
                    <span className="text-[12.5px] font-medium text-muted">
                      Issue {r.n} · {r.topic}
                    </span>
                    <span className="text-xs font-semibold whitespace-nowrap" style={{ color: TONE[cons.tone].fg }}>
                      {cons.label}
                    </span>
                  </div>
                  <Divide v="A" text={r.a} by={ids.filter((id) => r.votes[id] === "A").map((id) => nm(id))} color="#245C86" />
                  <Divide v="B" text={r.b} by={ids.filter((id) => r.votes[id] === "B").map((id) => nm(id))} color="#8F6A1E" />
                </div>
              ))}
              {divides.length === 0 && <span className="text-sm text-muted">The models shown agree on every issue they read.</span>}
            </div>
          </div>
        </>
      ) : (
        ids.length > 0 && <ReadingsOnly data={data} ids={ids} />
      )}

      {flagged.length > 0 && (
        <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
          <div className="flex items-center gap-2">
            <Dot color="#245C86" />
            <h3 className="m-0 font-serif text-base font-semibold">Facts the council flagged as decisive</h3>
          </div>
          <ul role="list" className="m-0 flex list-none flex-col gap-3.5 p-0">
            {flagged.map((f, i) => (
              <li key={i} className="flex flex-col gap-1.5 border-b border-line-4 pb-3.5 last:border-b-0 last:pb-0">
                <span className="font-serif text-[15px] leading-[1.55] text-ink">{f.t}</span>
                <span className="flex flex-wrap items-center gap-2 text-[12.5px] text-muted">
                  {f.ref && <span className="font-medium text-body-3">{f.ref}</span>}
                  {f.shownBy.length > 0 && (
                    <>
                      <span>
                        Flagged by {f.shownBy.length} of {ids.length} {ids.length === 1 ? "model" : "models"}
                      </span>
                      <MemberStack ids={f.shownBy} />
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-[10px] bg-sand px-[18px] py-3.5">
        <span className="min-w-[260px] flex-1 text-[13.5px] leading-[1.55] text-body-3">
          The council reads the record and the law. It does not decide the case or predict its outcome; each reading cites the documents and authorities it relies on.
        </span>
        <Link
          href={`/cases/${caseId}/ask`}
          className={cx(btn.outline, "flex h-[38px] items-center px-4 text-[13px] font-semibold text-ink hover:text-ink hover:no-underline")}
        >
          Ask the council a question →
        </Link>
      </div>
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

function Divide({ v, text, by, color }: { v: "A" | "B"; text: string; by: string[]; color: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <ReadingTag v={v} className="mt-0.5" />
      <div className="flex flex-col gap-[3px]">
        <span className="font-serif text-[14.5px] leading-normal text-ink">{text}</span>
        <span className="text-[12.5px]" style={{ color }}>
          {by.join(", ")}
        </span>
      </div>
    </div>
  );
}
