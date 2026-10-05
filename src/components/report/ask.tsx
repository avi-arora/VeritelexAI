"use client";

import { useRef, useState, type FormEvent } from "react";
import { api, isStatus, usePoll, type AskMode, type AskRequest, type AskSummary, type AskView as AskViewData } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Badge, Button, Segmented, card, cx } from "../ui";
import { Loading, useCase, useReport, useRuns } from "./case-context";
import { AskView, MODE_LABEL, askStatus } from "./ask-view";
import { MemberMono } from "./council-ui";

const MIN_Q = 5;
const MAX_Q = 2000;
/** Poll a running ask every 2.5 s (contract: every 2 to 3 s). */
const ASK_POLL_MS = 2500;

const MODES: { k: AskMode; label: string; hint: string }[] = [
  { k: "independent", label: "Independent", hint: "Each model answers on its own, without seeing the others." },
  { k: "debate", label: "Debate", hint: "The models review each other’s answers, then revise their own." },
  { k: "steelman", label: "Steel-man", hint: "The strongest case for each side, each point tied to the record." },
];

type Keyed<T> = { key: string; res?: T; err?: Error };

/** Ask the council: the question form, the selected question's answers (polled while running) and earlier questions. */
export function AskCouncil() {
  const { caseId } = useCase();
  const [sel, setSel] = useState<{ caseId: string; id: string } | null>(null);
  // The POST response, shown until the first poll of that ask returns.
  const [posted, setPosted] = useState<AskViewData | null>(null);
  const selId = sel?.caseId === caseId ? sel.id : null;

  const history = usePoll(() => api.asks(caseId), (list) => (list?.some((a) => a.status === "running") ? 5000 : null), [caseId]);

  // Results are keyed by ask id, so switching asks never shows the previous one's answers.
  // The last good result is kept (outside render) so a failed refresh does not blank the answers.
  const lastGood = useRef<{ key: string; res: AskViewData } | null>(null);
  const { data: polled } = usePoll<Keyed<AskViewData>>(
    selId
      ? async () => {
          try {
            const res = await api.getAsk(caseId, selId);
            lastGood.current = { key: selId, res };
            return { key: selId, res };
          } catch (e) {
            const keep = lastGood.current?.key === selId ? lastGood.current.res : undefined;
            return { key: selId, res: keep, err: e as Error };
          }
        }
      : null,
    (d) => {
      if (!d || d.key !== selId) return null;
      if (d.err) return isStatus(d.err, 404) ? null : 5000;
      return d.res?.status === "running" ? ASK_POLL_MS : null;
    },
    [caseId, selId],
  );
  const cur = polled?.key === selId ? polled : undefined;
  const view = cur?.res ?? (posted && posted.id === selId ? posted : undefined);

  const ask = async (body: AskRequest) => {
    const v = await api.createAsk(caseId, body);
    setPosted(v);
    setSel({ caseId, id: v.id });
    history.refresh();
  };

  return (
    <div className="flex flex-col gap-[18px]">
      <AskForm onAsk={ask} />

      {selId && (
        <div className="flex flex-col gap-2">
          {view ? <AskView view={view} /> : cur?.err ? null : <Loading label="Opening the question…" />}
          {cur?.err && (
            <p role="alert" className="m-0 text-sm text-red">
              {isStatus(cur.err, 404) ? "This question could not be found." : `Could not refresh the answers: ${cur.err.message}. Retrying…`}
            </p>
          )}
        </div>
      )}

      <History list={history.data} error={history.error} selectedId={selId} onOpen={(id) => setSel({ caseId, id })} />
    </div>
  );
}

function askErrorMessage(e: unknown) {
  const msg = (e as Error).message;
  if (isStatus(e, 409)) return msg && msg !== "Conflict" ? msg : "There is no report version to ground the question on yet.";
  if (isStatus(e, 429)) return "Three questions are already running for this case. Wait for one to finish, then ask again.";
  if (isStatus(e, 422)) return `The question was not accepted${msg && msg !== "Unprocessable Entity" ? `: ${msg}` : ". Check its length and scope."}`;
  return `Could not ask the council: ${msg}`;
}

const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

function AskForm({ onAsk }: { onAsk: (body: AskRequest) => Promise<void> }) {
  const { c, selectedRunId } = useCase();
  const { viewed, published } = useRuns();
  const { members, askIds, council, nm } = useStore();
  const { data: issuesData } = useReport("issues");
  const issues = issuesData?.issues ?? [];

  const [text, setText] = useState("");
  const [mode, setMode] = useState<AskMode>("independent");
  const [scopeKind, setScopeKind] = useState<"record" | "issue">("record");
  const [issuePick, setIssuePick] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // The picked issue, or the first one when the pick is not part of this version.
  const issueN = scopeKind === "issue" ? (issues.some((i) => i.n === issuePick) ? issuePick : (issues[0]?.n ?? null)) : null;
  const trimmed = text.trim();
  const excluded = members.filter((m) => !askIds.includes(m.id));
  const noMembers = !!council && askIds.length === 0;
  const noReport = !c?.reportReadyAt && !published;
  const canAsk = !busy && trimmed.length >= MIN_Q && trimmed.length <= MAX_Q && !noMembers && !noReport && (scopeKind === "record" || issueN != null);
  const n = council ? askIds.length : 0;

  const focus = scopeKind === "issue" ? issues.filter((i) => i.n === issueN) : issues.slice(0, 2);
  const chips = focus.flatMap((i) => [
    { q: `Which authorities govern Issue ${i.n} (${short(i.topic, 60)})?` },
    { q: `Which documents would resolve the disputed facts in Issue ${i.n}?` },
    { q: `What is the strongest case for each side on Issue ${i.n}?`, mode: "steelman" as const },
  ]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canAsk) return;
    setBusy(true);
    setErr("");
    try {
      await onAsk({
        question: trimmed,
        mode,
        scope: scopeKind === "issue" ? { kind: "issue", issue: issueN } : { kind: "record", issue: null },
        // Without the live member list, let the backend ask every configured member.
        ...(council ? { members: askIds } : {}),
        // Omitted for the published version.
        ...(selectedRunId ? { runId: selectedRunId } : {}),
      });
    } catch (e2) {
      setErr(askErrorMessage(e2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className={cx(card, "flex flex-col gap-4 px-6 py-[22px]")} noValidate>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <label htmlFor="ask-q" className="text-sm font-semibold text-ink">
          Your question about this case
        </label>
        <span id="ask-q-count" className={cx("text-xs", trimmed.length > 0 && trimmed.length < MIN_Q ? "text-amber" : "text-muted")}>
          {text.length} / {MAX_Q}
          {trimmed.length > 0 && trimmed.length < MIN_Q ? ` · at least ${MIN_Q} characters` : ""}
        </span>
      </div>
      <textarea
        id="ask-q"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            e.currentTarget.form?.requestSubmit();
          }
        }}
        rows={3}
        maxLength={MAX_Q}
        aria-describedby="ask-q-count"
        placeholder="For example: does the notice of 14 March satisfy clause 20.1?"
        className="w-full resize-y rounded-[10px] border border-field bg-white px-4 py-3.5 font-serif text-base leading-[1.55] text-ink focus:border-blue focus:shadow-[0_0_0_3px_var(--color-focus)] focus:outline-none"
      />

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Suggested</span>
          {chips.map((ch) => {
            const on = text === ch.q;
            return (
              <button
                key={ch.q}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setText(ch.q);
                  if (ch.mode) setMode(ch.mode);
                }}
                className="min-h-8 rounded-2xl border px-3 py-1 text-left text-[12.5px] font-medium"
                style={{ borderColor: on ? "#bcd2e4" : "#dcd8d2", background: on ? "#e8f0f7" : "#fff", color: on ? "#245C86" : "#3d434a" }}
              >
                {ch.q}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-6 border-t border-line-3 pt-3.5">
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-2 p-0 text-[12.5px] font-medium text-muted">Draw on</legend>
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                { k: "record", label: "Whole record" },
                { k: "issue", label: "One issue" },
              ] as const
            ).map((s) => {
              const on = scopeKind === s.k;
              const disabled = s.k === "issue" && issues.length === 0;
              return (
                <button
                  key={s.k}
                  type="button"
                  aria-pressed={on}
                  disabled={disabled}
                  onClick={() => setScopeKind(s.k)}
                  className={cx(
                    "h-[34px] rounded-lg border px-3 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-50",
                    on ? "border-navy bg-navy text-white" : "border-chip bg-white text-body-2",
                  )}
                >
                  {s.label}
                </button>
              );
            })}
            {scopeKind === "issue" && issues.length > 0 && (
              <select
                aria-label="Issue"
                value={issueN ?? ""}
                onChange={(e) => setIssuePick(Number(e.target.value))}
                className="h-[34px] max-w-[320px] rounded-lg border border-field bg-white px-2.5 text-[13px] text-ink focus:border-blue focus:outline-none"
              >
                {issues.map((i) => (
                  <option key={i.n} value={i.n}>
                    Issue {i.n} · {short(i.topic, 48)}
                  </option>
                ))}
              </select>
            )}
          </div>
        </fieldset>
        <div role="group" aria-labelledby="ask-mode-label" className="flex flex-col gap-2">
          <span id="ask-mode-label" className="text-[12.5px] font-medium text-muted">
            How the council answers
          </span>
          <Segmented options={MODES} value={mode} onChange={setMode} itemClassName="h-8 px-3 text-[13px]" />
        </div>
        <Button type="submit" variant="accent" className="ml-auto h-[42px] px-[22px] text-sm disabled:cursor-not-allowed disabled:opacity-60" disabled={!canAsk}>
          {busy ? "Asking…" : n ? `Ask ${n} ${n === 1 ? "model" : "models"}` : "Ask the council"}
        </Button>
      </div>
      <p className="m-0 -mt-1 text-[12.5px] text-muted">{MODES.find((m) => m.k === mode)?.hint}</p>

      <div className="flex flex-col gap-1.5 text-[12.5px] text-muted">
        {council ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">Asking</span>
            {askIds.map((id) => (
              <span key={id} className="flex items-center gap-1.5 rounded-md bg-sand py-0.5 pr-2 pl-0.5 text-body-2">
                <MemberMono id={id} size={18} />
                {nm(id)}
              </span>
            ))}
            {excluded.length > 0 && (
              <span>
                · Not asked:{" "}
                {excluded.map((m) => `${nm(m.id)} (${m.status === "unavailable" ? "not enabled in Model Garden" : "switched off in Settings"})`).join(", ")}
              </span>
            )}
          </div>
        ) : (
          <span>Every configured model will be asked.</span>
        )}
        {selectedRunId && viewed && <span>Answers will be grounded on version {viewed.version}, the version you are viewing.</span>}
      </div>

      {noMembers && <p className="m-0 text-sm text-amber">Switch on at least one available model in Settings to ask the council.</p>}
      {noReport && <p className="m-0 text-sm text-amber">The council can be asked once the analysis has produced a report.</p>}
      {err && (
        <p role="alert" className="m-0 text-sm text-red">
          {err}
        </p>
      )}
    </form>
  );
}

function History({ list, error, selectedId, onOpen }: { list?: AskSummary[]; error: Error | null; selectedId: string | null; onOpen: (id: string) => void }) {
  let body;
  if (list) {
    body = list.length ? (
      <ul role="list" className="m-0 list-none p-0">
        {list.map((a) => {
          const st = askStatus(a.status);
          const on = a.id === selectedId;
          return (
            <li key={a.id}>
              <button
                type="button"
                aria-current={on ? "true" : undefined}
                onClick={() => onOpen(a.id)}
                className={cx(
                  "grid w-full grid-cols-[minmax(0,1fr)_170px_150px] items-center gap-4 border-b border-line-4 px-6 py-3.5 text-left hover:bg-row-hover max-sm:grid-cols-1",
                  on ? "bg-blue-tint/60" : "bg-white",
                )}
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="line-clamp-2 font-serif text-[14.5px] leading-normal text-ink">{a.question}</span>
                  <span className="text-xs text-muted">
                    {a.scope.label}
                    {a.version != null ? ` · on version ${a.version}` : ""}
                  </span>
                </span>
                <span className="flex flex-col items-start gap-1 text-[13px] text-muted">
                  {MODE_LABEL[a.mode]}
                  <Badge tone={st.tone}>{st.label}</Badge>
                </span>
                <span className="text-right text-[13px] text-muted max-sm:text-left">{fmtDateTime(a.createdAt)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    ) : (
      <p className="m-0 px-6 py-4 text-sm text-muted">No questions have been put to the council on this case yet.</p>
    );
  } else if (error) {
    body = (
      <p className="m-0 px-6 py-4 text-sm text-muted">
        {isStatus(error, 404) ? "Earlier questions are not available yet." : `Could not load earlier questions: ${error.message}`}
      </p>
    );
  } else {
    body = (
      <div className="px-6 py-4">
        <Loading />
      </div>
    );
  }
  return (
    <section className={cx(card, "overflow-hidden")} aria-labelledby="ask-history">
      <div className="border-b border-line-2 px-6 py-4">
        <h3 id="ask-history" className="m-0 font-serif text-[15px] font-semibold">
          Earlier questions on this case
        </h3>
      </div>
      {body}
    </section>
  );
}
