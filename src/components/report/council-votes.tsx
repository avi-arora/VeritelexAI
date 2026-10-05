"use client";

import { Fragment } from "react";
import type { CouncilData, CouncilReading, CouncilRow, CouncilRunMemberSnapshot } from "@/lib/api";
import type { Tone } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Badge, ReadingTag, card, cx } from "../ui";
import { CiteList, MemberMono } from "./council-ui";

export type Consensus = { label: string; tone: Tone; unanimous: boolean; divided: boolean; agreed?: "A" | "B" };

/** Unanimous / Majority x–y / Split x–y among the shown members' votes, ignoring members that gave no reading. */
export function consensus(row: CouncilRow, ids: string[]): Consensus {
  const a = ids.filter((id) => row.votes[id] === "A").length;
  const b = ids.filter((id) => row.votes[id] === "B").length;
  if (a + b === 0) return { label: "No readings", tone: "grey", unanimous: false, divided: false };
  if (a + b === 1) return { label: "One reading", tone: "grey", unanimous: false, divided: false };
  if (!a || !b) return { label: "Unanimous", tone: "green", unanimous: true, divided: false, agreed: a ? "A" : "B" };
  if (a === b) return { label: `Split ${a}–${b}`, tone: "red", unanimous: false, divided: true };
  return { label: `Majority ${Math.max(a, b)}–${Math.min(a, b)}`, tone: "amber", unanimous: false, divided: true };
}

const fallbackOf = (members: CouncilRunMemberSnapshot[], id: string) => {
  const s = members.find((m) => m.id === id);
  return s ? { name: s.name, m: s.m, c: s.c } : undefined;
};

const CONFIDENCE: Record<CouncilReading["confidence"], { label: string; tone: Tone }> = {
  high: { label: "High confidence", tone: "green" },
  medium: { label: "Medium confidence", tone: "amber" },
  low: { label: "Low confidence", tone: "grey" },
};

/** Issue-by-issue votes of the shown members, with each member's own reading behind "Readings by model". */
export function VotesTable({ data, ids }: { data: CouncilData; ids: string[] }) {
  const { look } = useStore();
  return (
    <div className={cx(card, "overflow-hidden")}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-2 px-6 py-4">
        <h3 className="m-0 font-serif text-base font-semibold">Each model&apos;s reading, issue by issue</h3>
        <div className="flex gap-3.5 text-[12.5px] text-muted-2">
          <span className="flex items-center gap-1.5">
            <ReadingTag v="A" className="flex size-[18px] items-center justify-center rounded p-0 text-[10px]" />
            Majority reading
          </span>
          <span className="flex items-center gap-1.5">
            <ReadingTag v="B" className="flex size-[18px] items-center justify-center rounded p-0 text-[10px]" />
            Alternative reading
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse">
          <colgroup>
            <col />
            {ids.map((id) => (
              <col key={id} className="w-[60px]" />
            ))}
            <col className="w-[150px]" />
          </colgroup>
          <thead>
            <tr className="border-b border-line-2 bg-panel">
              <th scope="col" className="px-6 py-3 text-left text-[12.5px] font-medium text-muted">
                Legal issue and readings
              </th>
              {ids.map((id) => (
                <th key={id} scope="col" className="px-1 py-3">
                  <span className="flex justify-center">
                    <MemberMono id={id} fallback={fallbackOf(data.members, id)} size={26} />
                  </span>
                  <span className="sr-only">{look(id, fallbackOf(data.members, id)).name}</span>
                </th>
              ))}
              <th scope="col" className="px-6 py-3 text-right text-[12.5px] font-medium text-muted">
                Council
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => {
              const cons = consensus(r, ids);
              const readings = r.readings.filter((x) => ids.includes(x.member));
              return (
                <Fragment key={r.n}>
                  <tr className="border-t border-line-4 first:border-t-0">
                    <th scope="row" className="px-6 pt-[18px] pb-2 text-left align-top font-normal">
                      <div className="flex min-w-0 flex-col gap-[7px]">
                        <span className="font-serif text-[15.5px] font-semibold text-ink">
                          {r.n}. {r.topic}
                        </span>
                        {r.a && <Reading v="A" text={r.a} />}
                        {r.b && <Reading v="B" text={r.b} />}
                      </div>
                    </th>
                    {ids.map((id) => (
                      <td key={id} className="px-1 pt-[18px] align-top">
                        <Vote v={r.votes[id] ?? "-"} />
                      </td>
                    ))}
                    <td className="px-6 pt-[18px] text-right align-top">
                      <Badge tone={cons.tone} className="px-[9px] py-1 text-xs whitespace-nowrap">
                        {cons.label}
                      </Badge>
                    </td>
                  </tr>
                  <tr>
                    <td colSpan={ids.length + 2} className="px-6 pb-4">
                      {readings.length > 0 && (
                        <details className="group">
                          <summary className="cursor-pointer text-[13px] font-medium text-blue">Readings by model ({readings.length})</summary>
                          <div className="pt-3">
                            <ReadingList readings={readings} members={data.members} />
                          </div>
                        </details>
                      )}
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Vote({ v }: { v: "A" | "B" | "-" }) {
  if (v === "-") {
    return (
      <span className="mx-auto flex size-[30px] items-center justify-center rounded-[7px] bg-panel text-[13px] text-muted-3">
        <span aria-hidden>–</span>
        <span className="sr-only">No reading</span>
      </span>
    );
  }
  return (
    <span
      className="mx-auto flex size-[30px] items-center justify-center rounded-[7px] text-[13px] font-semibold"
      style={{ background: v === "A" ? "#e8f0f7" : "#f7f0e0", color: v === "A" ? "#245C86" : "#8F6A1E" }}
    >
      {v}
    </span>
  );
}

function Reading({ v, text }: { v: "A" | "B"; text: string }) {
  return (
    <div className="flex items-start gap-2">
      <ReadingTag v={v} />
      <span className="text-[13.5px] leading-normal text-body-2">{text}</span>
    </div>
  );
}

/** Each member's own reading of one issue: text, what it turns on, confidence and citations. */
export function ReadingList({ readings, members }: { readings: CouncilReading[]; members: CouncilRunMemberSnapshot[] }) {
  const { look } = useStore();
  return (
    <ul role="list" className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 p-0">
      {readings.map((x) => {
        const conf = CONFIDENCE[x.confidence] ?? CONFIDENCE.low;
        return (
          <li key={x.member} className="flex flex-col gap-2.5 rounded-lg border border-line-2 bg-white px-4 py-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <MemberMono id={x.member} fallback={fallbackOf(members, x.member)} size={22} />
              <span className="text-[13.5px] font-semibold text-ink">{look(x.member, fallbackOf(members, x.member)).name}</span>
              <Badge tone={conf.tone} className="ml-auto rounded px-1.5 py-px text-[11px]">
                {conf.label}
              </Badge>
            </div>
            <p className="m-0 max-w-[75ch] font-serif text-[14.5px] leading-[1.6] whitespace-pre-line text-ink">{x.text}</p>
            {x.turnsOn && (
              <p className="m-0 max-w-[75ch] text-[13px] leading-[1.5] text-body-3">
                <span className="font-medium text-body-2">Turns on: </span>
                {x.turnsOn}
              </p>
            )}
            <CiteList cites={x.cites} />
          </li>
        );
      })}
    </ul>
  );
}

/** compared === false: the readings could not be lined up, so each issue lists every shown member's reading. */
export function ReadingsOnly({ data, ids }: { data: CouncilData; ids: string[] }) {
  return (
    <div className="flex flex-col gap-4">
      {data.rows.map((r) => {
        const readings = r.readings.filter((x) => ids.includes(x.member));
        return (
          <section key={r.n} className={cx(card, "flex flex-col gap-3.5 px-6 py-5")} aria-labelledby={`council-issue-${r.n}`}>
            <h3 id={`council-issue-${r.n}`} className="m-0 font-serif text-[15.5px] font-semibold text-ink">
              {r.n}. {r.topic}
            </h3>
            {readings.length ? (
              <ReadingList readings={readings} members={data.members} />
            ) : (
              <span className="text-sm text-muted">No reading from the models shown.</span>
            )}
          </section>
        );
      })}
    </div>
  );
}
