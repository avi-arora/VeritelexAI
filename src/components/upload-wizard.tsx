"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { ApiError, UploadError, api, putToSignedUrl, usePoll, type CaseField, type UploadFailure, type UploadTarget } from "@/lib/api";
import { CONNECTORS, PIPELINE } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Button, Spinner, card, cx, input } from "./ui";

const STEPS = ["Add documents", "Confirm case details", "Grounding and models"];
const ACCEPT = ".pdf,.docx,.xlsx,.png,.jpg,.jpeg,.tif,.tiff,.txt";
const EXT_LABEL: Record<string, string> = { pdf: "PDF", docx: "DOC", xlsx: "XLS", png: "IMG", jpg: "IMG", jpeg: "IMG", tif: "IMG", tiff: "IMG", txt: "TXT" };
const MAX_BYTES = 500 * 1024 * 1024;
const MIME: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", tif: "image/tiff", tiff: "image/tiff", txt: "text/plain",
};
const CASE_ID = /^c[0-9a-f]{12}$/;
const PARALLEL_UPLOADS = 3;
const PUT_ATTEMPTS = 3; // per file, for network blips; each attempt restarts the file
const CHECK_ATTEMPTS = 4; // the server-side check is idempotent

type Phase = "ready" | "queued" | "preparing" | "uploading" | "verifying" | "uploaded" | "failed";
type Item = {
  key: string;
  file: File;
  ext: string;
  phase: Phase;
  sent: number; // bytes sent in the current attempt
  rate?: number; // average bytes per second of the current attempt
  error?: string;
  failure?: UploadFailure;
  docId?: string; // server record of the latest attempt
  landed?: boolean; // the bytes are in Cloud Storage; only the server check is outstanding
};

const IN_FLIGHT: Phase[] = ["queued", "preparing", "uploading", "verifying"];
const BADGE: Record<Phase, [label: string, tone: string]> = {
  ready: ["Ready to upload", "bg-blue-wash text-blue"],
  queued: ["Waiting", "bg-sand text-muted-2"],
  preparing: ["Preparing", "bg-sand text-muted-2"],
  uploading: ["Uploading", "bg-blue-wash text-blue"],
  verifying: ["Checking", "bg-blue-wash text-blue"],
  uploaded: ["Uploaded ✓", "bg-[#eef6f0] text-green"],
  failed: ["Failed", "bg-[#f8eae8] text-red"],
};
const BAR =
  "block h-1.5 w-full appearance-none overflow-hidden rounded-full border-0 bg-line-2 [&::-webkit-progress-bar]:bg-line-2 [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:transition-[width] [&::-webkit-progress-value]:duration-300 [&::-moz-progress-bar]:rounded-full";
const BAR_TONE = {
  blue: "[&::-webkit-progress-value]:bg-blue [&::-moz-progress-bar]:bg-blue",
  green: "[&::-webkit-progress-value]:bg-green [&::-moz-progress-bar]:bg-green",
  red: "[&::-webkit-progress-value]:bg-red [&::-moz-progress-bar]:bg-red",
};

let lastKey = 0;
const extOf = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";
const fmtSize = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const fmtLeft = (s: number) => (s < 60 ? `${Math.max(1, Math.round(s))} s` : `${Math.round(s / 60)} min`);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const pctOf = (part: number, whole: number) => (whole > 0 ? Math.min(100, Math.floor((part * 100) / whole)) : 0);

/** PUT with automatic retries for network blips. Each attempt restarts the file, so progress resets to 0. */
async function putWithRetry(target: UploadTarget, file: File, onProgress: (sent: number) => void) {
  for (let attempt = 1; ; attempt++) {
    onProgress(0);
    try {
      return await putToSignedUrl(target, file, onProgress);
    } catch (e) {
      if (!(e instanceof UploadError) || e.kind !== "transient" || attempt >= PUT_ATTEMPTS) throw e;
      await sleep(2000 * attempt);
    }
  }
}

/** Ask the server to check the landed file. Idempotent, so transient failures are retried. */
async function completeWithRetry(caseId: string, docId: string) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await api.completeUpload(caseId, docId);
    } catch (e) {
      const transient = !(e instanceof ApiError) || e.status >= 500 || e.status === 429;
      if (!transient || attempt >= CHECK_ATTEMPTS) throw e;
      await sleep(1000 * 2 ** (attempt - 1));
    }
  }
}

/** A message for the file's row, and what can be done about the failure. */
function describe(e: unknown, fileName: string): { error: string; failure: UploadFailure } {
  if (e instanceof UploadError) return { error: e.message, failure: e.kind };
  if (e instanceof ApiError) {
    const msg = e.message.startsWith(`${fileName}: `) ? e.message.slice(fileName.length + 2) : e.message;
    const error = msg ? msg.charAt(0).toUpperCase() + msg.slice(1) : "The server could not check the file.";
    if (e.status === 422) return { error, failure: "fatal" }; // the file itself was refused
    if (e.status === 404 || e.status === 409) return { error, failure: "link" }; // record gone or cancelled: send it again
    return { error, failure: "transient" };
  }
  return { error: "Could not reach the server. Check the connection and retry.", failure: "transient" };
}

function detail(f: Item): string {
  switch (f.phase) {
    case "preparing":
      return "Getting a secure upload link…";
    case "queued":
      return "Waiting for a free upload slot";
    case "uploading": {
      const parts = [`${fmtSize(f.sent)} of ${fmtSize(f.file.size)}`];
      if (f.rate) parts.push(`${fmtSize(f.rate)}/s`, `about ${fmtLeft((f.file.size - f.sent) / f.rate)} left`);
      return parts.join(" · ");
    }
    case "verifying":
      return "Checking the file type and contents…";
    case "uploaded":
      return "Uploaded and checked";
    default:
      return "";
  }
}

export function UploadWizard({ initialStep, initialCaseId }: { initialStep: 1 | 2 | 3; initialCaseId?: string }) {
  const router = useRouter();
  const { conn, members, showToast } = useStore();
  const validCase = initialCaseId && CASE_ID.test(initialCaseId) ? initialCaseId : null;
  const [step, setStep] = useState<1 | 2 | 3>(validCase ? initialStep : 1);
  const [caseId, setCaseId] = useState<string | null>(validCase);
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const sources = CONNECTORS.filter((c) => c.available && conn[c.id]);
  // The analysis runs every configured council member that is enabled in Model Garden.
  const councilOn = members.filter((m) => m.status !== "unavailable");
  const councilOff = members.filter((m) => m.status === "unavailable");

  // Leaving the page would cut off the uploads in flight.
  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  const addFiles = (list: FileList | null) => {
    if (!list || busy) return;
    const next: Item[] = [];
    const bad: string[] = [];
    for (const file of Array.from(list)) {
      const ext = extOf(file.name);
      if (!EXT_LABEL[ext] || file.size === 0 || file.size > MAX_BYTES) bad.push(file.name);
      else if (!items.some((i) => i.file.name === file.name && i.file.size === file.size)) next.push({ key: `f${++lastKey}`, file, ext, phase: "ready", sent: 0 });
    }
    setItems((cur) => [...cur, ...next].slice(0, 50));
    setError(bad.length ? `Not added (unsupported type, empty or over 500 MB): ${bad.join(", ")}` : "");
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    addFiles(e.dataTransfer.files);
  };

  const patch = (key: string, p: Partial<Item>) => setItems((cur) => cur.map((it) => (it.key === key ? { ...it, ...p } : it)));

  const advance = (id: string) => {
    router.replace(`/upload?case=${id}&step=2`, { scroll: false });
    setStep(2);
  };

  async function upload() {
    const todo = items.filter((it) => it.phase === "ready" || (it.phase === "failed" && it.failure !== "fatal"));
    if (!todo.length) {
      if (caseId && items.some((it) => it.phase === "uploaded")) advance(caseId);
      return;
    }
    const keys = new Set(todo.map((it) => it.key));
    setBusy(true);
    setError("");
    setItems((cur) => cur.map((it) => (keys.has(it.key) ? { ...it, phase: "preparing", error: undefined, failure: undefined } : it)));
    try {
      const id = caseId ?? (await api.createCase()).id;
      setCaseId(id);
      // A file whose bytes already landed only needs the server check again; the rest need a new link.
      const targets = new Map<string, UploadTarget>();
      const needLink = todo.filter((it) => !(it.landed && it.docId));
      if (needLink.length) {
        const res = await api.requestUploads(id, needLink.map((it) => ({ name: it.file.name, size: it.file.size, contentType: MIME[it.ext] })));
        needLink.forEach((it, i) => targets.set(it.key, res.targets[i]));
        // Close the records these links replace: a pending record holds back the analysis.
        await Promise.allSettled(needLink.flatMap((it) => (it.docId ? [api.abandonUpload(id, it.docId)] : [])));
      }
      setItems((cur) =>
        cur.map((it) => {
          const t = targets.get(it.key);
          if (t) return { ...it, phase: "queued", docId: t.documentId, landed: false, sent: 0, rate: undefined };
          return keys.has(it.key) ? { ...it, phase: "queued" } : it;
        }),
      );

      // Up to PARALLEL_UPLOADS files at a time, straight to Cloud Storage.
      let cursor = 0;
      let ok = 0;
      const worker = async () => {
        while (cursor < todo.length) {
          const it = todo[cursor++];
          const target = targets.get(it.key);
          try {
            if (target) {
              const size = it.file.size;
              const minStep = Math.max(size / 200, 256 * 1024); // re-render at most ~200 times per file
              let started = Date.now();
              let shown = 0;
              patch(it.key, { phase: "uploading" });
              await putWithRetry(target, it.file, (sent) => {
                if (sent === 0) started = Date.now();
                else if (sent < size && sent - shown < minStep) return;
                shown = sent;
                const secs = (Date.now() - started) / 1000;
                patch(it.key, { sent, rate: sent > 0 && secs >= 1 ? sent / secs : undefined });
              });
              patch(it.key, { landed: true, sent: size });
            }
            patch(it.key, { phase: "verifying" });
            await completeWithRetry(id, target?.documentId ?? it.docId!);
            patch(it.key, { phase: "uploaded" });
            ok++;
          } catch (e) {
            patch(it.key, { phase: "failed", ...describe(e, it.file.name) });
          }
        }
      };
      await Promise.all(Array.from({ length: PARALLEL_UPLOADS }, worker));

      const before = items.filter((it) => !keys.has(it.key));
      const failed = todo.length - ok + before.filter((it) => it.phase === "failed").length;
      if (failed === 0) {
        const n = before.length + ok;
        showToast(`${n} file${n === 1 ? "" : "s"} uploaded`);
        advance(id);
      } else {
        setError(`${failed} file${failed === 1 ? "" : "s"} could not be uploaded. Retry, remove ${failed === 1 ? "it" : "them"}, or continue without ${failed === 1 ? "it" : "them"}.`);
      }
    } catch (e) {
      // Creating the case or the upload links failed: nothing was sent.
      const msg = e instanceof ApiError && e.message ? e.message : "Could not reach the server. Check the connection and retry.";
      setItems((cur) =>
        cur.map((it) =>
          keys.has(it.key) && IN_FLIGHT.includes(it.phase) ? (it.docId ? { ...it, phase: "failed", error: msg, failure: "transient" } : { ...it, phase: "ready" }) : it,
        ),
      );
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  /** Go on with the files that made it; close the failed ones so the analysis can start. */
  async function skipFailed() {
    if (!caseId) return;
    const failed = items.filter((it) => it.phase === "failed");
    setBusy(true);
    setError("");
    const results = await Promise.allSettled(failed.flatMap((it) => (it.docId ? [api.abandonUpload(caseId, it.docId)] : [])));
    setBusy(false);
    // 409: the file made it after all. Anything else leaves a pending record that holds back the analysis.
    if (results.some((r) => r.status === "rejected" && !(r.reason instanceof ApiError && r.reason.status === 409))) {
      setError("Could not skip the failed files. Check the connection and try again.");
      return;
    }
    setItems((cur) => cur.filter((it) => it.phase !== "failed"));
    advance(caseId);
  }

  const remove = (it: Item) => {
    setItems((cur) => cur.filter((x) => x.key !== it.key));
    if (caseId && it.docId && it.phase === "failed") {
      api.abandonUpload(caseId, it.docId).catch(() => setError(`Could not remove ${it.file.name} from the case. It may delay the analysis by a few minutes.`));
    }
  };

  const uploadedCount = items.filter((i) => i.phase === "uploaded").length;
  const failedCount = items.filter((i) => i.phase === "failed").length;
  const retryable = items.filter((i) => i.phase === "failed" && i.failure !== "fatal").length;
  const readyCount = items.filter((i) => i.phase === "ready").length;
  const started = items.some((i) => i.phase !== "ready");
  const totalBytes = items.reduce((a, i) => a + i.file.size, 0);
  const sentBytes = items.reduce((a, i) => a + (i.phase === "uploaded" || i.phase === "verifying" ? i.file.size : i.phase === "uploading" ? i.sent : 0), 0);
  const canUpload = readyCount > 0 || retryable > 0 || (uploadedCount > 0 && failedCount === 0);

  return (
    <div className="mx-auto grid max-w-[1180px] grid-cols-[minmax(0,1fr)_320px] items-start gap-8 px-7 pt-9 pb-16 max-lg:grid-cols-1">
      <div className="flex min-w-0 flex-col gap-6">
        <div>
          <h1 className="mb-2 font-serif text-[30px] leading-[1.2] font-semibold">New case from documents</h1>
          <p className="m-0 text-[15px] leading-[1.6] text-muted-2">
            Upload the case papers. We read them, propose the case details for you to confirm, and create the case entry.
          </p>
        </div>

        <ol className="m-0 flex list-none flex-wrap gap-2 p-0">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const cur = step === n;
            const done = step > n;
            return (
              <li
                key={label}
                aria-current={cur ? "step" : undefined}
                className={cx("flex min-w-[180px] flex-1 items-center gap-3 rounded-[10px] border px-4 py-3.5", cur ? "border-blue bg-white" : "border-line bg-transparent")}
              >
                <span
                  className="flex size-7 flex-none items-center justify-center rounded-full text-[13px] font-semibold"
                  style={{ background: done ? "#2E6B4F" : cur ? "#245C86" : "#ecebe7", color: done || cur ? "#fff" : "#80878f" }}
                >
                  {done ? "✓" : n}
                </span>
                <span className={cx("text-sm font-medium", cur || done ? "text-ink" : "text-muted")}>{label}</span>
              </li>
            );
          })}
        </ol>

        {step === 1 && (
          <div className="flex flex-col gap-5">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
              className={cx(
                "flex flex-col items-center gap-3 rounded-[14px] border-2 border-dashed px-8 py-12 text-center",
                drag ? "border-blue bg-blue-wash" : "border-[#cfcac3] bg-white",
              )}
            >
              <div className="flex size-[52px] items-center justify-center rounded-xl bg-blue-wash text-[26px] text-blue">↑</div>
              <span className="text-[17px] font-semibold text-ink">Drag files here</span>
              <span className="text-sm text-muted">PDF, Word, Excel or scanned images · up to 500 MB each</span>
              <input ref={picker} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
              <div className="mt-2 flex flex-wrap justify-center gap-2.5">
                <Button className="h-[42px] px-[18px] text-sm" onClick={() => picker.current?.click()} disabled={busy}>Choose files</Button>
                <Button variant="outline" className="h-[42px] px-[18px] text-sm" disabled title="Not available in this pilot">Import from DIFC eRegistry</Button>
              </div>
            </div>
            {items.length > 0 && (
              <div className={cx(card, "overflow-hidden")}>
                <div className="flex flex-col gap-3 border-b border-line-2 px-[22px] py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    {started ? (
                      <output className="text-[15px] font-semibold">
                        {busy ? "Uploading · " : ""}
                        {uploadedCount} of {items.length} uploaded{failedCount ? ` · ${failedCount} failed` : ""}
                      </output>
                    ) : (
                      <span className="text-[15px] font-semibold">{items.length} file{items.length === 1 ? "" : "s"} added</span>
                    )}
                    <span className="text-[13px] text-muted">
                      {started
                        ? `${fmtSize(sentBytes)} of ${fmtSize(totalBytes)} · ${pctOf(sentBytes, totalBytes)}%`
                        : `${fmtSize(totalBytes)} · document types detected automatically`}
                    </span>
                  </div>
                  {started && (
                    <progress
                      max={totalBytes}
                      value={sentBytes}
                      aria-label="Overall upload progress"
                      className={cx(BAR, uploadedCount === items.length ? BAR_TONE.green : BAR_TONE.blue)}
                    />
                  )}
                </div>
                <ul className="m-0 list-none p-0">
                  {items.map((f) => {
                    const [label, tone] = BADGE[f.phase];
                    const value = f.phase === "uploaded" || f.phase === "verifying" ? f.file.size : f.sent;
                    const note = f.phase === "failed" ? f.error : detail(f);
                    return (
                      <li
                        key={f.key}
                        className="grid grid-cols-[36px_minmax(0,1fr)_150px_80px_24px] items-center gap-3.5 border-b border-line-4 px-[22px] py-3.5 last:border-b-0 max-sm:grid-cols-[36px_minmax(0,1fr)_24px]"
                      >
                        <div className="flex h-[38px] w-8 items-end justify-center rounded border border-field bg-panel pb-1 font-mono text-[8px] font-semibold text-muted">{EXT_LABEL[f.ext]}</div>
                        <div className="flex min-w-0 flex-col gap-1.5">
                          <span className="truncate text-sm font-medium text-ink">{f.file.name}</span>
                          {f.phase !== "ready" && (
                            <progress
                              max={f.file.size}
                              value={value}
                              aria-label={`Upload progress for ${f.file.name}`}
                              className={cx(BAR, f.phase === "uploaded" ? BAR_TONE.green : f.phase === "failed" ? BAR_TONE.red : BAR_TONE.blue)}
                            />
                          )}
                          {note && (
                            <span className={cx("truncate text-xs", f.phase === "failed" ? "text-red" : "text-muted")} title={note}>
                              {note}
                            </span>
                          )}
                        </div>
                        <span className={cx("flex items-center gap-2 justify-self-start rounded-[5px] px-[9px] py-1 text-[12.5px] font-medium max-sm:hidden", tone)}>
                          {(f.phase === "preparing" || f.phase === "uploading" || f.phase === "verifying") && <Spinner />}
                          {f.phase === "uploading" ? `${label} ${pctOf(value, f.file.size)}%` : label}
                        </span>
                        <span className="text-[13px] text-muted max-sm:hidden">{fmtSize(f.file.size)}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${f.file.name}`}
                          disabled={busy || f.phase === "uploaded"}
                          onClick={() => remove(f)}
                          className="text-base text-faint disabled:opacity-30"
                        >
                          ×
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {error && <p className="m-0 text-sm text-red">{error}</p>}
            <div className="flex flex-wrap justify-end gap-3">
              {!busy && failedCount > 0 && uploadedCount > 0 && (
                <Button variant="outline" className="h-[46px] px-5 text-sm" onClick={skipFailed}>
                  Continue without {failedCount === 1 ? "the failed file" : `the ${failedCount} failed files`}
                </Button>
              )}
              <Button className="h-[46px] px-6 text-sm" onClick={upload} disabled={busy || !canUpload}>
                {busy ? "Uploading…" : retryable > 0 && readyCount === 0 ? `Retry ${retryable === 1 ? "the failed upload" : `${retryable} failed uploads`}` : "Upload and continue"}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && caseId && <ConfirmDetails caseId={caseId} onBack={() => setStep(1)} onDone={() => setStep(3)} />}

        {step === 3 && (
          <div className="flex flex-col gap-5">
            <div className={cx(card, "px-[26px] py-6")}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <h3 className="m-0 font-serif text-[17px] font-semibold">Ground the analysis in</h3>
                <Link href="/settings/connectors" className="text-[13px] font-medium">Manage connectors</Link>
              </div>
              <p className="mt-0 mb-4 text-[13.5px] text-muted">Only connected sources are listed. Every statement in the report will cite one of these or the case record.</p>
              <div className="grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
                {sources.map((g) => (
                  <div key={g.id} className="flex items-center gap-3 rounded-lg border border-line px-3.5 py-3">
                    <span className="flex size-[18px] flex-none items-center justify-center rounded bg-blue text-[11px] font-semibold text-white">✓</span>
                    <span className="text-sm font-medium">{g.name}</span>
                  </div>
                ))}
                {sources.length === 0 && <span className="text-sm text-muted">No grounding source is connected — only the case record will be used.</span>}
              </div>
            </div>
            <div className={cx(card, "px-[26px] py-6")}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <h3 className="m-0 font-serif text-[17px] font-semibold">Model council</h3>
                <Link href="/settings/council" className="text-[13px] font-medium">Change models</Link>
              </div>
              <p className="mt-0 mb-4 text-[13.5px] text-muted">
                {members.length
                  ? `${councilOn.length} ${councilOn.length === 1 ? "model" : "models"} will read the record independently when the report is generated, and their readings will be compared.`
                  : "The model council will read the record independently when the report is generated, and the readings will be compared."}
              </p>
              <div className="flex flex-wrap gap-2">
                {councilOn.map((m) => (
                  <span key={m.id} className="rounded-md bg-sand px-3 py-[7px] text-[13px] font-medium">{m.name}</span>
                ))}
              </div>
              {councilOff.length > 0 && (
                <p className="mt-3 mb-0 text-[13px] text-muted">
                  Not enabled in Model Garden, so skipped: {councilOff.map((m) => m.name).join(", ")}.
                </p>
              )}
            </div>
            <div className="flex justify-between">
              <Button variant="outline" className="h-[46px] px-5 text-sm" onClick={() => setStep(2)}>Back</Button>
              <Button
                variant="accent"
                className="h-[46px] px-6 text-sm"
                onClick={() => {
                  showToast("Case created · analysis running");
                  router.push("/cases");
                }}
              >
                Create case and follow the analysis
              </Button>
            </div>
          </div>
        )}
      </div>

      <aside className={cx(card, "sticky top-[88px] p-6 max-lg:static")}>
        <h3 className="mb-1.5 font-serif text-base font-semibold">What happens next</h3>
        <p className="mt-0 mb-5 text-[13px] leading-[1.55] text-muted">You can follow each stage from the Cases list.</p>
        <div className="flex flex-col">
          {PIPELINE.map((p) => (
            <div key={p.t} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
              <div className="flex flex-col items-center">
                <span className="mt-1 size-3 flex-none rounded-full" style={{ background: p.c }} />
                <span className="min-h-5 w-0.5 flex-1 bg-line-2" />
              </div>
              <div className="pb-[18px]">
                <span className="mb-[3px] block text-sm font-semibold text-ink">{p.t}</span>
                <span className="text-[13px] leading-normal text-muted-2">{p.b}</span>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

/** Step 2: the Background agent fills in the case profile; poll until it has, then let the user confirm. */
function ConfirmDetails({ caseId, onBack, onDone }: { caseId: string; onBack: () => void; onDone: () => void }) {
  const { data: c, error } = usePoll(() => api.getCase(caseId), (d) => (d && (d.fields.length > 0 || d.status === "action") ? null : 3000), [caseId]);
  // User edits; until the first edit the agent-extracted values are shown.
  const [edited, setFields] = useState<CaseField[] | null>(null);
  const fields = edited ?? (c && c.fields.length > 0 ? c.fields : null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const save = async () => {
    if (!fields) return;
    setSaving(true);
    setSaveError("");
    try {
      await api.updateCase(caseId, { fields, confirmed: true });
      onDone();
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {!fields && c?.status !== "action" && (
        <div className="flex items-center gap-3 rounded-[10px] border border-line bg-white px-[18px] py-3.5">
          <Spinner />
          <span className="text-sm leading-normal text-body-3">
            Reading the documents and extracting the case details… {c?.note ? <span className="text-muted">({c.note})</span> : null}
          </span>
        </div>
      )}
      {c?.status === "action" && !fields && (
        <div className="rounded-[10px] border border-[#ecc9c4] bg-[#f8eae8] px-[18px] py-3.5 text-sm text-red">
          {c.note} · <Link href={`/cases/${caseId}/docs`}>Open the case</Link>
        </div>
      )}
      {error && <p className="m-0 text-sm text-red">{error.message}</p>}
      {fields && (
        <>
          <div className="flex items-center gap-3 rounded-[10px] border border-[#cfe3d5] bg-[#eef6f0] px-[18px] py-3.5">
            <span className="flex size-[22px] flex-none items-center justify-center rounded-full bg-green text-xs font-semibold text-white">✓</span>
            <span className="text-sm leading-normal text-[#24543e]">
              We read the case papers and filled in the details below. Check each one before the case is created.
            </span>
          </div>
          <div className={cx(card, "grid grid-cols-2 gap-x-6 gap-y-[22px] p-[26px] max-sm:grid-cols-1")}>
            {fields.map((f, i) => (
              <label key={f.k} className={cx("flex flex-col gap-2", f.full && "col-span-full")}>
                <span className="text-[13px] font-medium text-body-2">{f.k}</span>
                <input
                  value={f.v}
                  maxLength={500}
                  onChange={(e) => setFields(fields.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))}
                  className={input}
                />
                <span className="text-xs text-muted-3">{f.src}</span>
              </label>
            ))}
          </div>
        </>
      )}
      {saveError && <p className="m-0 text-sm text-red">{saveError}</p>}
      <div className="flex justify-between">
        <Button variant="outline" className="h-[46px] px-5 text-sm" onClick={onBack}>Back</Button>
        <Button className="h-[46px] px-6 text-sm" onClick={save} disabled={!fields || saving}>{saving ? "Saving…" : "Continue"}</Button>
      </div>
    </div>
  );
}
