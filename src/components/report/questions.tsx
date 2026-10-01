"use client";

import { COUNSEL_QS, MODELS } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Button, Dot, Monogram, card, cx } from "../ui";

export function CounselQuestions() {
  const { models, enabledIds, pinned, togglePin, setExportOpen } = useStore();

  const qs = COUNSEL_QS.map((x, i) => ({ ...x, i, by: x.by.filter((id) => models[id]) }))
    .filter((x) => x.by.length > 0)
    .sort((a, b) => b.by.length - a.by.length);
  const pinnedN = Object.values(pinned).filter(Boolean).length;

  const groups = [
    { label: "For the Claimant", c: "#245C86", items: qs.filter((x) => x.to === "Claimant") },
    { label: "For the Defendant", c: "#8a8378", items: qs.filter((x) => x.to === "Defendant") },
  ];

  return (
    <div className="flex flex-col gap-[18px]">
      <div className="flex flex-wrap items-center gap-3.5 rounded-[10px] border border-line bg-white px-[18px] py-3.5">
        <span className="flex-1 text-sm font-medium text-ink">
          {pinnedN} {pinnedN === 1 ? "question" : "questions"} added to the bench note for the trial on 19 Oct 2026
        </span>
        <Button className="h-[38px] px-4 text-[13px]" onClick={() => setExportOpen(true)}>Print bench note</Button>
      </div>
      <div className="grid grid-cols-2 items-start gap-4 max-md:grid-cols-1">
        {groups.map((grp) => (
          <div key={grp.label} className="flex flex-col gap-3">
            <div className="flex items-center gap-2 px-1">
              <Dot color={grp.c} square />
              <span className="text-[15px] font-semibold">{grp.label}</span>
            </div>
            {grp.items.map((x) => {
              const on = !!pinned[x.i];
              return (
                <div key={x.i} className={cx(card, "flex flex-col gap-3 px-[22px] py-5")}>
                  <p className="text-pretty m-0 font-serif text-base leading-[1.55] text-ink">{x.q}</p>
                  <span className="text-[13px] leading-normal text-muted-2">{x.why}</span>
                  <div className="flex flex-wrap gap-3.5 text-[12.5px]">
                    <span className="font-medium text-blue">Issue {x.iss}</span>
                    <span className="text-muted">{x.ref}</span>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-4 pt-3">
                    <div className="flex items-center gap-2">
                      <div className="flex gap-[3px]">
                        {x.by.map((id) => {
                          const m = MODELS.find((mm) => mm.id === id)!;
                          return <Monogram key={id} m={m.m} c={m.c} size={20} radius={5} fontSize={9} />;
                        })}
                      </div>
                      <span className="text-[12.5px] text-muted-2">Raised by {x.by.length} of {enabledIds.length} models</span>
                    </div>
                    <button
                      type="button"
                      aria-pressed={on}
                      onClick={() => togglePin(x.i)}
                      className="h-8 rounded-[7px] border px-3 text-[12.5px] font-semibold whitespace-nowrap"
                      style={{ borderColor: on ? "#cfe3d5" : "#d6d2cc", background: on ? "#e7f0ea" : "#fff", color: on ? "#2E6B4F" : "#1a1d21" }}
                    >
                      {on ? "In bench note ✓" : "Add to bench note"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
