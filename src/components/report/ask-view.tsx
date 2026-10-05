"use client";

import type { AskAnswer, AskMode, AskReview, AskSynthesis, AskView as AskViewData, SteelPoint } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Badge, Dot, Spinner, card, cx } from "../ui";
import { CiteList, ExternalLink, MemberChip, MemberMono, MemberStack, Mentions } from "./council-ui";

export const MODE_LABEL: Record<AskMode, string> = {
  independent: "Independent answers",
  debate: "Debate",
  steelman: "Strongest case for each side",
};

const ASK_STATUS = {
  running: { label: "Answering", tone: "blue" },
  succeeded: { label: "Answered", tone: "green" },
  partial: { label: "Partly answered", tone: "amber" },
  failed: { label: "Failed", tone: "red" },
} as const;
export const askStatus = (s: AskViewData["status"]) => ASK_STATUS[s] ?? ASK_STATUS.failed;

const waiting = (s: string) => s === "pending" || s === "queued" || s === "running" || s === "retrying";

/** One question put to the council: every member's answer as it arrives, the review round, the synthesis. */
export function AskView({ view }: { view: AskViewData }) {
  const { nm } = useStore();
  const answers = view.members.map((id) => view.answers.find((a) => a.member === id) ?? placeholder(id));
  const st = askStatus(view.status);
  const n = view.members.length;
  const answered = answers.filter((a) => a.status === "succeeded").map((a) => a.member);
  const models = `${n} ${n === 1 ? "model" : "models"}`;
  // Nothing to compare with fewer than two answers; in steel-man mode the chair merges points instead of comparing.
  const compare = view.mode !== "steelman" && answered.length >= 2;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5 px-0.5 py-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] font-medium text-muted">
          <Badge tone={st.tone}>{st.label}</Badge>
          {[MODE_LABEL[view.mode], view.scope.label, view.version != null ? `on version ${view.version}` : "", view.status === "running" ? models : `${answered.length} of ${models} answered`, fmtDateTime(view.createdAt)]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <p className="m-0 font-serif text-lg leading-normal whitespace-pre-line text-ink">{view.question}</p>
      </div>

      {view.status === "running" && (
        <div role="status" className="flex items-center gap-2.5 text-[14px] font-medium text-blue">
          <Spinner />
          {progressLabel(view)}
        </div>
      )}

      {view.mode === "steelman" ? (
        <>
          <div className="flex flex-wrap gap-1.5">
            {answers.map((a) => (
              <MemberChip key={a.member} id={a.member} status={a.status} error={a.error} showDone />
            ))}
          </div>
          <SteelColumns
            claimant={view.steelman?.claimant ?? answers.flatMap((a) => a.claimant.map((p) => withBy(p, a.member)))}
            defendant={view.steelman?.defendant ?? answers.flatMap((a) => a.defendant.map((p) => withBy(p, a.member)))}
            merged={!!view.steelman}
            chaired={!!view.synthesis?.chair}
            pending={answers.some((a) => waiting(a.status))}
            names={answered.map((id) => nm(id))}
          />
        </>
      ) : (
        <div className="overflow-x-auto pb-1">
          <ul
            role="list"
            className="m-0 grid list-none gap-3.5 p-0"
            style={{ gridTemplateColumns: n <= 3 ? `repeat(${Math.max(n, 1)}, minmax(0,1fr))` : `repeat(${n}, minmax(300px,1fr))` }}
          >
            {answers.map((a) => (
              <AnswerCard key={a.member} a={a} />
            ))}
          </ul>
        </div>
      )}

      {view.mode === "debate" && (
        <ReviewRound reviews={view.reviews} members={view.members} answered={answered} answersPending={answers.some((a) => waiting(a.status))} />
      )}

      {view.synthesis ? (
        <Synthesis s={view.synthesis} compare={compare} />
      ) : (
        view.status === "running" && view.mode !== "steelman" && (
          <div className={cx(card, "px-6 py-5 text-sm text-muted")}>The chair will draw the answers together once every model has answered.</div>
        )
      )}
    </div>
  );
}

function placeholder(member: string): AskAnswer {
  return { member, status: "queued", model: null, error: null, paragraphs: [], turnsOnDisputedFact: false, cites: [], claimant: [], defendant: [] };
}

const withBy = (p: SteelPoint, member: string): SteelPoint => (p.by?.length ? p : { ...p, by: [member] });

function progressLabel(v: AskViewData) {
  const done = v.answers.filter((a) => !waiting(a.status)).length;
  if (done < v.members.length) return `The council is answering — ${done} of ${v.members.length} models done…`;
  if (v.mode === "debate" && v.reviews.some((r) => waiting(r.status))) return "The models are reviewing each other’s answers…";
  return "The chair is drawing the answers together…";
}

function AnswerCard({ a }: { a: AskAnswer }) {
  const { look, member, anon } = useStore();
  const l = look(a.member);
  const live = member(a.member);
  const sub = anon ? "" : a.model || live?.host || "";
  return (
    <li className={cx(card, "flex min-w-0 flex-col")}>
      <div className="flex items-center gap-3 border-b border-line-2 px-[18px] py-4">
        <MemberMono id={a.member} size={34} dim={a.status === "unavailable" || a.status === "failed"} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14.5px] font-semibold">{l.name}</span>
          {sub && <span className="truncate text-xs text-muted">{sub}</span>}
        </div>
        {a.turnsOnDisputedFact && a.status === "succeeded" && (
          <Badge tone="amber" className="rounded px-1.5 py-[3px] text-[11px] whitespace-nowrap">
            Turns on a disputed fact
          </Badge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-[18px]">
        {waiting(a.status) && (
          <span className="flex items-center gap-2 text-sm text-blue">
            <Spinner />
            {a.status === "retrying" ? "Retrying…" : a.status === "running" ? "Reading the record…" : "Waiting to start…"}
          </span>
        )}
        {a.status === "succeeded" &&
          (a.paragraphs.length ? (
            a.paragraphs.map((p, i) => (
              <p key={i} className="m-0 font-serif text-[14.5px] leading-[1.65] whitespace-pre-line text-prose">
                {p}
              </p>
            ))
          ) : (
            <span className="text-sm text-muted">No answer text was returned.</span>
          ))}
        {a.status === "unavailable" && (
          <div className="flex flex-col gap-1.5 text-sm text-body-3">
            <span>Not enabled in Model Garden.</span>
            <ExternalLink href={live?.consoleUrl} className="text-[13px] font-medium">
              Enable in Model Garden
            </ExternalLink>
          </div>
        )}
        {a.status === "failed" && <span className="text-sm leading-[1.55] break-words text-red">{a.error || "This model could not answer."}</span>}
        {a.status === "skipped" && <span className="text-sm text-muted">Skipped.</span>}
      </div>
      {a.status === "succeeded" && (
        <div className="flex flex-col gap-[9px] border-t border-line-3 px-[18px] py-3.5">
          <span className="text-xs font-medium text-muted">Citations</span>
          <CiteList cites={a.cites} />
        </div>
      )}
    </li>
  );
}

function SteelColumns({ claimant, defendant, merged, pending, names }: { claimant: SteelPoint[]; defendant: SteelPoint[]; merged: boolean; pending: boolean; names: string[] }) {
  const cols = [
    { t: "Strongest case for the Claimant", c: "#245C86", items: claimant },
    { t: "Strongest case for the Defendant", c: "#8a8378", items: defendant },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
      {cols.map((col) => (
        <section key={col.t} className={cx(card, "flex flex-col gap-3.5 border-t-[3px] px-6 py-[22px]")} style={{ borderTopColor: col.c }} aria-label={col.t}>
          <h3 className="m-0 font-serif text-base font-semibold">{col.t}</h3>
          {col.items.length ? (
            <ul role="list" className="m-0 flex list-none flex-col gap-4 p-0">
              {col.items.map((p, i) => (
                <li key={i} className="flex gap-3">
                  <span aria-hidden className="flex-none pt-[3px] font-mono text-[13px] font-medium text-muted-3">
                    —
                  </span>
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <p className="m-0 font-serif text-[15.5px] leading-[1.65] text-prose">{p.point}</p>
                    {p.by.length > 0 && (
                      <span className="flex items-center gap-2 text-xs text-muted">
                        Made by <MemberStack ids={p.by} size={18} />
                      </span>
                    )}
                    {p.cites.length > 0 && <CiteList cites={p.cites} />}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-sm text-muted">{pending ? "Waiting for the models…" : "No points were made for this side."}</span>
          )}
          <span className="mt-auto text-[12.5px] text-muted">
            {merged ? `Combined by the chair from ${names.join(", ")}.` : "Each model’s own points, until the chair combines them."}
          </span>
        </section>
      ))}
    </div>
  );
}

function ReviewRound({ reviews, members, answersPending }: { reviews: AskReview[]; members: string[]; answersPending: boolean }) {
  const { nm } = useStore();
  const ordered = [...reviews].sort((a, b) => members.indexOf(a.member) - members.indexOf(b.member));
  return (
    <section className={cx(card, "flex flex-col gap-3.5 px-6 py-[22px]")} aria-label="Review round">
      <h3 className="m-0 font-serif text-base font-semibold">Review round — the models check each other</h3>
      {ordered.length === 0 && (
        <span className="text-sm text-muted">{answersPending ? "The review starts once every model has answered." : "No reviews were returned."}</span>
      )}
      {ordered.map((r) => (
        <div key={r.member} className="flex flex-col gap-2.5 border-b border-line-4 pb-3.5 last:border-b-0 last:pb-0">
          <span className="flex items-center gap-2 text-[13.5px] font-semibold text-ink">
            <MemberMono id={r.member} size={20} />
            {nm(r.member)}
            {waiting(r.status) && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-blue">
                <Spinner className="size-3 border" />
                Reviewing the other answers…
              </span>
            )}
          </span>
          {r.status === "failed" && <span className="text-sm text-red">{r.error || "This review failed."}</span>}
          {r.status === "unavailable" && <span className="text-sm text-muted">Not enabled in Model Garden.</span>}
          {r.notes.map((note, i) => (
            <div key={i} className="grid grid-cols-[240px_minmax(0,1fr)] gap-4 max-sm:grid-cols-1">
              <span className="text-[13.5px] font-medium text-ink">
                {nm(r.member)} <span className="font-normal text-muted">on {nm(note.about)}’s answer</span>
              </span>
              <span className="text-sm leading-[1.6] text-body-2">
                <Mentions text={note.point} />
              </span>
            </div>
          ))}
          {r.revised && (
            <div className="grid grid-cols-[240px_minmax(0,1fr)] gap-4 max-sm:grid-cols-1">
              <span className="text-[13.5px] font-medium text-[#24543e]">Revised position</span>
              <span className="text-sm leading-[1.6] font-medium text-[#24543e]">
                <Mentions text={r.revised} />
              </span>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

function Synthesis({ s }: { s: AskSynthesis }) {
  const { nm, anon } = useStore();
  const chair = s.chair ? `${nm(s.chair)}${!anon && s.model ? ` (${s.model})` : ""}` : "";
  const cols = [
    { t: "Where they agree", c: "#2E6B4F", items: s.agree, empty: "No point on which every model agrees." },
    { t: "Where they differ", c: "#B07A18", items: s.differ, empty: "No material difference between the models." },
    { t: "Left out", c: "#9B3E35", items: s.leftOut, empty: "Every citation was verified.", plain: true },
  ];
  return (
    <section className={cx(card, "flex flex-col gap-5 px-[26px] py-6")} aria-label="Synthesis">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 font-serif text-base font-semibold">Synthesis</h3>
        {chair && <span className="text-[12.5px] text-muted">Drawn up by {chair}</span>}
      </div>
      {waiting(s.status) && (
        <span className="flex items-center gap-2 text-sm text-blue">
          <Spinner />
          The chair is drawing the answers together…
        </span>
      )}
      {s.status === "failed" && <span className="text-sm text-red">{s.error || "The synthesis could not be produced."}</span>}
      {s.status === "succeeded" && (
        <>
          {s.summary && (
            <p className="m-0 font-serif text-[15.5px] leading-[1.65] whitespace-pre-line text-prose">
              <Mentions text={s.summary} />
            </p>
          )}
          <div className="grid grid-cols-3 gap-6 max-md:grid-cols-1">
            {cols.map((col) => (
              <div key={col.t} className="flex flex-col gap-2.5">
                <div className="flex items-center gap-2">
                  <Dot color={col.c} />
                  <span className="text-[14.5px] font-semibold">{col.t}</span>
                </div>
                {col.items.length ? (
                  <ul role="list" className="m-0 flex list-none flex-col gap-2 p-0">
                    {col.items.map((it, i) => (
                      <li key={i} className="text-sm leading-[1.6] break-words text-body-2">
                        {col.plain ? it : <Mentions text={it} />}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="m-0 text-sm leading-[1.6] text-muted">{col.empty}</p>
                )}
              </div>
            ))}
          </div>
          {s.leftOut.length > 0 && <span className="text-xs text-muted">Left out: citations that could not be verified against the record or the verified authorities.</span>}
        </>
      )}
    </section>
  );
}
