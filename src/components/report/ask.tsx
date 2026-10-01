"use client";

import { useState } from "react";
import { CITE_ST, MODELS, PRESETS, type Answer, type ModelId } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Button, DashList, Dot, Monogram, Segmented, Spinner, card, cx } from "../ui";
import { useCouncilRun } from "./council";

type Mode = "independent" | "debate" | "steel";
type Scope = "record" | "issue" | "docs";

const MODES = [
  { k: "independent", label: "Independent answers" },
  { k: "debate", label: "Debate · models review each other" },
  { k: "steel", label: "Strongest case for each side" },
] as const;

const SCOPES: { k: Scope; label: string }[] = [
  { k: "record", label: "Whole record and connectors" },
  { k: "issue", label: "Issue 3 papers only" },
  { k: "docs", label: "Selected documents" },
];

export function AskCouncil() {
  const { enabledIds: ids, nm } = useStore();
  const [preset, setPreset] = useState(0);
  const [text, setText] = useState(PRESETS[0].q);
  const [mode, setMode] = useState<Mode>("independent");
  const [scope, setScope] = useState<Scope>("record");
  const [running, run] = useCouncilRun();

  const PR = PRESETS[preset];
  const n = ids.length;
  const pick = (i: number) => {
    setPreset(i);
    setText(PRESETS[i].q);
  };

  const synth = PR.synth(ids, nm);
  const synthesis = [
    { t: "Where they agree", c: "#2E6B4F", items: synth.agree },
    { t: "Where they differ", c: "#B07A18", items: synth.differ.length ? synth.differ : ["No material difference between the enabled models."] },
    { t: "Left out", c: "#9B3E35", items: synth.out.length ? synth.out : ["All citations were verified against a connected source."] },
  ];
  const review = PR.review.filter((x) => ids.includes(x.from) && ids.includes(x.to));

  return (
    <div className="flex flex-col gap-[18px]">
      <div className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")}>
        <label htmlFor="ask-q" className="text-sm font-semibold text-ink">Your question about this case</label>
        <textarea
          id="ask-q"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-[10px] border border-field bg-white px-4 py-3.5 font-serif text-base leading-[1.55] text-ink focus:border-blue focus:shadow-[0_0_0_3px_var(--color-focus)] focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Suggested</span>
          {PRESETS.map((p, i) => {
            const on = preset === i;
            return (
              <button
                key={p.label}
                type="button"
                aria-pressed={on}
                onClick={() => pick(i)}
                className="h-8 rounded-2xl border px-3 text-[12.5px] font-medium whitespace-nowrap"
                style={{ borderColor: on ? "#bcd2e4" : "#dcd8d2", background: on ? "#e8f0f7" : "#fff", color: on ? "#245C86" : "#3d434a" }}
              >
                {p.label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-end gap-6 border-t border-line-3 pt-3.5">
          <div className="flex flex-col gap-2">
            <span className="text-[12.5px] font-medium text-muted">Draw on</span>
            <div className="flex flex-wrap gap-1.5">
              {SCOPES.map((s) => {
                const on = scope === s.k;
                return (
                  <button
                    key={s.k}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setScope(s.k)}
                    className={cx("h-[34px] rounded-lg border px-3 text-[13px] font-medium", on ? "border-navy bg-navy text-white" : "border-chip bg-white text-body-2")}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-[12.5px] font-medium text-muted">How the council answers</span>
            <Segmented options={MODES} value={mode} onChange={setMode} itemClassName="h-8 px-3 text-[13px]" />
          </div>
          <Button variant="accent" className="ml-auto h-[42px] px-[22px] text-sm" onClick={run} disabled={running}>
            Ask {n} models
          </Button>
        </div>
      </div>

      {running ? (
        <div className={cx(card, "flex items-center gap-3 p-7 text-blue")}>
          <Spinner />
          <span className="text-[14.5px] font-medium">The council is answering — {n} models working independently…</span>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5 px-0.5 py-1">
            <span className="text-[12.5px] font-medium text-muted">
              {MODES.find((m) => m.k === mode)!.label} · {SCOPES.find((s) => s.k === scope)!.label} · {n} models
            </span>
            <span className="font-serif text-lg leading-normal text-ink">{text.trim() || PR.q}</span>
          </div>

          {mode === "steel" ? (
            <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
              {[
                { t: "Strongest case for the Claimant", c: "#245C86", items: PR.steel.c },
                { t: "Strongest case for the Defendant", c: "#8a8378", items: PR.steel.d },
              ].map((col) => (
                <div key={col.t} className={cx(card, "flex flex-col gap-3.5 border-t-[3px] px-6 py-[22px]")} style={{ borderTopColor: col.c }}>
                  <span className="font-serif text-base font-semibold">{col.t}</span>
                  <DashList items={col.items} />
                  <span className="mt-auto text-[12.5px] text-muted">Combined from {ids.map(nm).join(", ")}. Each point cites the record.</span>
                </div>
              ))}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto pb-1">
                <div
                  className="grid gap-3.5"
                  style={{ gridTemplateColumns: n <= 3 ? `repeat(${n}, minmax(0,1fr))` : `repeat(${n}, minmax(300px,1fr))` }}
                >
                  {ids.map((id) => (
                    <AnswerCard key={id} id={id} name={nm(id)} answer={PR.answers[id]} />
                  ))}
                </div>
              </div>

              {mode === "debate" && (
                <div className={cx(card, "flex flex-col gap-3.5 px-6 py-[22px]")}>
                  <span className="font-serif text-base font-semibold">Review round — the models check each other</span>
                  {review.map((r) => (
                    <div key={r.from + r.to + r.t} className="grid grid-cols-[240px_minmax(0,1fr)] gap-4 border-b border-line-4 pb-3 max-sm:grid-cols-1">
                      <span className="text-[13.5px] font-semibold text-ink">
                        {nm(r.from)} <span className="font-normal text-muted">{r.self ? "revises its answer" : `on ${nm(r.to)}`}</span>
                      </span>
                      <span className="text-sm leading-[1.6] text-body-2">{r.t}</span>
                    </div>
                  ))}
                  <span className="text-sm leading-[1.6] font-medium text-[#24543e]">{PR.outcome}</span>
                </div>
              )}

              <div className={cx(card, "grid grid-cols-3 gap-6 px-[26px] py-6 max-md:grid-cols-1")}>
                {synthesis.map((s) => (
                  <div key={s.t} className="flex flex-col gap-2.5">
                    <div className="flex items-center gap-2">
                      <Dot color={s.c} />
                      <span className="text-[14.5px] font-semibold">{s.t}</span>
                    </div>
                    {s.items.map((it) => (
                      <p key={it} className="m-0 text-sm leading-[1.6] text-body-2">{it}</p>
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className={cx(card, "overflow-hidden")}>
        <div className="border-b border-line-2 px-6 py-4">
          <span className="font-serif text-[15px] font-semibold">Earlier questions on this case</span>
        </div>
        {PRESETS.map((p, i) => (
          <button
            key={p.q}
            type="button"
            onClick={() => pick(i)}
            className="grid w-full grid-cols-[minmax(0,1fr)_150px_120px] items-center gap-4 border-b border-line-4 bg-white px-6 py-3.5 text-left hover:bg-row-hover max-sm:grid-cols-1"
          >
            <span className="font-serif text-[14.5px] leading-normal text-ink">{p.q}</span>
            <span className="text-[13px] text-muted">{p.mode}</span>
            <span className="text-right text-[13px] text-muted max-sm:text-left">{p.when}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function AnswerCard({ id, name, answer }: { id: ModelId; name: string; answer: Answer }) {
  const m = MODELS.find((x) => x.id === id)!;
  return (
    <div className={cx(card, "flex min-w-0 flex-col")}>
      <div className="flex items-center gap-3 border-b border-line-2 px-[18px] py-4">
        <Monogram m={m.m} c={m.c} size={34} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14.5px] font-semibold">{name}</span>
          <span className="truncate text-xs text-muted">{m.host}</span>
        </div>
        <span className="font-mono text-xs text-muted-3">{answer.time}</span>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-[18px]">
        {answer.paras.map((p) => (
          <p key={p} className="m-0 font-serif text-[14.5px] leading-[1.65] text-prose">{p}</p>
        ))}
      </div>
      <div className="flex flex-col gap-[9px] border-t border-line-3 px-[18px] py-3.5">
        <span className="text-xs font-medium text-muted">Citations</span>
        {answer.cites.map((ct) => {
          const s = CITE_ST[ct.st];
          return (
            <div key={ct.t} className="flex items-start gap-[9px]">
              <span className="mt-px flex size-[18px] flex-none items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: s.bg }}>
                {s.icon}
              </span>
              <div className="flex min-w-0 flex-col gap-px">
                <span className="text-[13px] leading-[1.4] font-medium text-ink">{ct.t}</span>
                <span className="text-xs" style={{ color: s.noteFg }}>{ct.note}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
