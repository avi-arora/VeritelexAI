"use client";

import { useState, type ReactNode } from "react";
import { isStatus, type CounselQuestion, type QuestionsData } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, Dot, Segmented, card, cx } from "../ui";
import { Loading, RunProgress, useCase, useReport, useRuns } from "./case-context";
import { CouncilNotRun, MemberStack } from "./council-ui";

type Party = CounselQuestion["to"];
type Filter = "all" | Party;

const GROUPS: { to: Party; label: string; c: string }[] = [
  { to: "Claimant", label: "For the Claimant", c: "#245C86" },
  { to: "Defendant", label: "For the Defendant", c: "#8a8378" },
  { to: "Both", label: "For both parties", c: "#5c646d" },
];

const FILTERS: { k: Filter; label: string }[] = [
  { k: "all", label: "All parties" },
  { k: "Claimant", label: "Claimant" },
  { k: "Defendant", label: "Defendant" },
  { k: "Both", label: "Both" },
];

/** Questions for counsel suggested by the council for the version being viewed. */
export function CounselQuestions() {
  const { c } = useCase();
  const { published } = useRuns();
  const { data, runId, error, loading } = useReport("questions");
  if (data) return <QuestionsView data={data} runId={runId} />;
  if (loading) return <Loading />;
  if (error && !isStatus(error, 404)) return <p className="text-sm text-red">Could not load the questions for counsel: {error.message}</p>;
  if (!c?.reportReadyAt && !published) return <RunProgress />;
  return <CouncilNotRun what="questions" />;
}

function QuestionsView({ data, runId }: { data: QuestionsData; runId?: string }) {
  const { isOn, members, pinned, togglePin, setExportOpen } = useStore();
  const { caseId } = useCase();
  const { viewed } = useRuns();
  const [filter, setFilter] = useState<Filter>("all");
  // Question ids ("q1") repeat across cases and versions, so pins are kept per case and version.
  const pinKey = (id: string) => `${caseId}/${runId ?? ""}/${id}`;

  // Members switched off in Settings are left out, as in the other council views.
  const all = data.questions.map((q) => ({ ...q, by: q.by.filter((id) => isOn(id)) }));
  const qs = [...all.filter((q) => q.by.length > 0)].sort((a, b) => b.by.length - a.by.length);
  const hiddenN = all.length - qs.length;
  // "Raised by x of y": y = members that answered in this version (and are shown), else the live council.
  const answered = viewed?.council.filter((m) => m.status === "succeeded" && isOn(m.id)).length;
  const total = answered || members.filter((m) => isOn(m.id)).length;
  const pinnedN = qs.filter((q) => pinned[pinKey(q.id)]).length;

  const groups = GROUPS.filter((g) => filter === "all" || g.to === filter).map((g) => ({ ...g, items: qs.filter((q) => q.to === g.to) }));
  const sideBySide = filter === "all" ? groups.filter((g) => g.to !== "Both") : [];
  const stacked = filter === "all" ? groups.filter((g) => g.to === "Both" && g.items.length > 0) : groups;

  return (
    <div className="flex flex-col gap-[18px]">
      <div className="flex flex-wrap items-center gap-3.5 rounded-[10px] border border-line bg-white px-[18px] py-3.5">
        <span className="flex-1 text-sm font-medium text-ink">
          {pinnedN} {pinnedN === 1 ? "question" : "questions"} added to the bench note
        </span>
        <Button className="h-[38px] px-4 text-[13px]" onClick={() => setExportOpen(true)}>
          Print bench note
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented options={FILTERS} value={filter} onChange={setFilter} itemClassName="h-[34px] px-3.5 text-[13px]" />
        {hiddenN > 0 && (
          <span className="text-[13px] text-muted">
            {hiddenN} {hiddenN === 1 ? "question was" : "questions were"} raised only by models switched off in Settings.
          </span>
        )}
      </div>

      {qs.length === 0 && <div className={cx(card, "px-6 py-5 text-sm text-body-3")}>The council suggested no questions for counsel in this version.</div>}

      {sideBySide.length > 0 && qs.length > 0 && (
        <div className="grid grid-cols-2 items-start gap-4 max-md:grid-cols-1">
          {sideBySide.map((g) => (
            <Group key={g.to} label={g.label} c={g.c}>
              {g.items.map((q) => (
                <QuestionCard key={q.id} q={q} total={total} on={!!pinned[pinKey(q.id)]} onPin={() => togglePin(pinKey(q.id))} />
              ))}
              {g.items.length === 0 && <span className="px-1 text-sm text-muted">No questions for this party.</span>}
            </Group>
          ))}
        </div>
      )}
      {stacked.map((g) => (
        <Group key={g.to} label={g.label} c={g.c}>
          <div className="grid grid-cols-2 items-start gap-4 max-md:grid-cols-1">
            {g.items.map((q) => (
              <QuestionCard key={q.id} q={q} total={total} on={!!pinned[pinKey(q.id)]} onPin={() => togglePin(pinKey(q.id))} />
            ))}
          </div>
          {g.items.length === 0 && <span className="px-1 text-sm text-muted">No questions for this party.</span>}
        </Group>
      ))}
    </div>
  );
}

function Group({ label, c, children }: { label: string; c: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3" aria-label={label}>
      <div className="flex items-center gap-2 px-1">
        <Dot color={c} square />
        <h3 className="m-0 text-[15px] font-semibold">{label}</h3>
      </div>
      {children}
    </section>
  );
}

function QuestionCard({ q, total, on, onPin }: { q: CounselQuestion; total: number; on: boolean; onPin: () => void }) {
  const of = Math.max(total, q.by.length);
  return (
    <div className={cx(card, "flex flex-col gap-3 px-[22px] py-5")}>
      <p className="text-pretty m-0 font-serif text-base leading-[1.55] text-ink">{q.q}</p>
      {q.why && <span className="text-[13px] leading-normal text-muted-2">{q.why}</span>}
      <div className="flex flex-wrap gap-3.5 text-[12.5px]">
        {q.iss > 0 && <span className="font-medium text-blue">Issue {q.iss}</span>}
        {q.ref && <span className="text-muted">{q.ref}</span>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-4 pt-3">
        <div className="flex items-center gap-2">
          <MemberStack ids={q.by} />
          <span className="text-[12.5px] text-muted-2">
            Raised by {q.by.length} of {of} {of === 1 ? "model" : "models"}
          </span>
        </div>
        <button
          type="button"
          aria-pressed={on}
          onClick={onPin}
          className="h-8 rounded-[7px] border px-3 text-[12.5px] font-semibold whitespace-nowrap"
          style={{ borderColor: on ? "#cfe3d5" : "#d6d2cc", background: on ? "#e7f0ea" : "#fff", color: on ? "#2E6B4F" : "#1a1d21" }}
        >
          {on ? "In bench note ✓" : "Add to bench note"}
        </button>
      </div>
    </div>
  );
}
