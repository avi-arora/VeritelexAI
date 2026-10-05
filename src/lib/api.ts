"use client";

// Typed client for the VeriteLex backend. The browser only talks to this app's
// own origin (/api/v1/*); the Next.js route handler forwards to the FastAPI
// service, so no backend URL or credential ever reaches the client.

import { useCallback, useEffect, useRef, useState } from "react";
import type { CaseStatus, ChronoEntry, Coverage, Decision, Tone } from "./data";

export type ApiCaseSummary = {
  id: string;
  no: string;
  title: string;
  type: string;
  division: string;
  docs: string;
  pages: string;
  status: CaseStatus;
  pct?: number | null;
  at?: number | null;
  note: string;
  updated: string;
  updatedAt: string;
  past?: boolean;
  isNew?: boolean;
};

export type CaseField = { k: string; v: string; src: string; full: boolean };

export type ApiCaseDetail = ApiCaseSummary & {
  subtitle: string;
  reportReadyAt: string | null;
  fields: CaseField[];
  latestRunId: string | null;
};

export type ApiDocument = { id: string; n: string; t: string; p: string; ext: string; by: string; s: string; tone: Tone; status: string; sizeBytes?: number | null };

export type UploadTarget = { documentId: string; name: string; uploadUrl: string; method: "PUT"; headers: Record<string, string> };

export type StepView = {
  id: string; agent: string; status: string; attempts: number; error?: string | null; startedAt?: string | null; finishedAt?: string | null;
  /** Set on succeeded steps only: "unavailable" = council member not enabled in Model Garden. */
  outcome?: "unavailable" | "skipped" | null;
  /** Council re-runs: result reused from the source version, not recomputed. */
  reused?: boolean;
};
export type RunMode = "full" | "council";
export type RunView = {
  id: string; status: string; stage: string; pct: number; createdAt: string; updatedAt: string; steps: StepView[];
  mode?: RunMode; sourceRunId?: string | null;
};

/* ───────────── Model council and report versions (see the council API contract) ───────────── */

export type CouncilMemberStatus = "ready" | "fallback" | "unavailable" | "error" | "unknown";
export type CouncilMember = {
  id: string; name: string; vendor: string; host: string;
  /** Monogram and colour. */
  m: string; c: string;
  /** Fallback chain; the first entry is preferred. */
  models: string[];
  status: CouncilMemberStatus;
  activeModel: string | null;
  detail: string;
  /** Model Garden page where the model is enabled. */
  consoleUrl: string;
  checkedAt: string | null;
};
/** `chair` is the synthesis order. */
export type CouncilModels = { chair: string[]; members: CouncilMember[] };

export type StepState = "pending" | "queued" | "running" | "retrying" | "succeeded" | "failed" | "unavailable" | "skipped";
export type CouncilRunMember = { id: string; status: StepState; model: string | null; error: string | null };
export type RunStatus = "running" | "succeeded" | "partial" | "failed";
/** One analysis run = one report version. */
export type RunSummary = {
  id: string;
  version: number;
  status: RunStatus;
  mode: RunMode;
  trigger: "upload" | "manual" | "council";
  sourceRunId: string | null;
  sourceVersion: number | null;
  createdAt: string;
  finishedAt: string | null;
  stage: string;
  pct: number;
  hasReport: boolean;
  published: boolean;
  docCount: number;
  counts: { facts: number; issues: number; decisions: number } | null;
  council: CouncilRunMember[];
};

export type CiteStatus = "verified" | "warn" | "bad";
export type CouncilCite = { kind: "record" | "authority"; text: string; status: CiteStatus; note: string };
export type CouncilReading = { member: string; text: string; turnsOn: string; confidence: "high" | "medium" | "low"; cites: CouncilCite[] };
export type Vote = "A" | "B" | "-";
export type CouncilRow = { n: number; topic: string; a: string; b: string; votes: Record<string, Vote>; readings: CouncilReading[] };
export type CouncilRunMemberSnapshot = { id: string; name: string; m: string; c: string; status: "succeeded" | "failed" | "unavailable"; model: string | null; error: string | null };
export type CouncilData = {
  ranAt: string;
  durationS: number | null;
  chair: { id: string; model: string } | null;
  /** false: the readings could not be compared automatically (a, b and votes are empty). */
  compared: boolean;
  note: string;
  members: CouncilRunMemberSnapshot[];
  rows: CouncilRow[];
  flagged: { t: string; ref: string; by: string[] }[];
};
export type CounselQuestion = { id: string; to: "Claimant" | "Defendant" | "Both"; q: string; why: string; iss: number; ref: string; by: string[] };
export type QuestionsData = { questions: CounselQuestion[] };

export type AskMode = "independent" | "debate" | "steelman";
export type AskRequest = {
  question: string;
  mode: AskMode;
  scope: { kind: "record" | "issue"; issue?: number | null };
  members?: string[];
  runId?: string;
};
export type AskScope = { kind: "record" | "issue"; issue: number | null; label: string };
export type AskStatus = "running" | "succeeded" | "partial" | "failed";
export type AskSummary = {
  id: string; question: string; mode: AskMode; scope: AskScope; status: AskStatus;
  runId: string; version: number | null; createdAt: string; finishedAt: string | null;
};
export type SteelPoint = { point: string; cites: CouncilCite[]; by: string[] };
export type AskAnswer = {
  member: string; status: StepState; model: string | null; error: string | null;
  paragraphs: string[];
  turnsOnDisputedFact: boolean;
  cites: CouncilCite[];
  claimant: SteelPoint[];
  defendant: SteelPoint[];
};
/** Debate mode. Text fields may contain member mentions ({{m:id}}). */
export type AskReview = { member: string; status: StepState; error: string | null; notes: { about: string; point: string }[]; revised: string };
export type AskSynthesis = {
  status: StepState; chair: string | null; model: string | null; error: string | null;
  /** summary, agree and differ may contain member mentions ({{m:id}}). */
  summary: string; agree: string[]; differ: string[];
  /** Citations that could not be verified (computed, not model-judged). */
  leftOut: string[];
};
export type AskView = AskSummary & {
  members: string[];
  answers: AskAnswer[];
  reviews: AskReview[];
  synthesis: AskSynthesis | null;
  steelman: { claimant: SteelPoint[]; defendant: SteelPoint[] } | null;
};

export type BackgroundData = { paragraphs: string[]; keyFacts: { k: string; v: string }[]; fields: CaseField[]; counts: Record<string, number> };
export type MatrixData = { entries: ChronoEntry[] };
export type MappingData = { groups: { facts: number[]; d: string; t: string; iss: string; decisions: Decision[] }[]; totalDecisions: number; excluded: number };
export type IssueData = { n: number; topic: string; q: string; law: string; st: string; tone: Tone; facts: string };
export type IssuesData = { issues: IssueData[] };
export type ToolsData = {
  sources: Record<string, { short: string; type: string; meta: string; sum: string; auth: string[]; cov: [Coverage, string][] }>;
  verification: Record<string, number>;
};
export type ReportData = {
  background: BackgroundData; matrix: MatrixData; mapping: MappingData; issues: IssuesData; tools: ToolsData;
  council: CouncilData; questions: QuestionsData;
};
export type ReportKey = keyof ReportData;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") msg = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  listCases: () => call<ApiCaseSummary[]>("/cases"),
  getCase: (id: string) => call<ApiCaseDetail>(`/cases/${encodeURIComponent(id)}`),
  createCase: () => call<ApiCaseDetail>("/cases", { method: "POST", body: "{}" }),
  updateCase: (id: string, body: { fields?: CaseField[]; confirmed?: boolean }) =>
    call<ApiCaseDetail>(`/cases/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  documents: (id: string) => call<ApiDocument[]>(`/cases/${encodeURIComponent(id)}/documents`),
  requestUploads: (id: string, files: { name: string; size: number; contentType: string }[]) =>
    call<{ caseId: string; targets: UploadTarget[] }>(`/cases/${encodeURIComponent(id)}/uploads`, { method: "POST", body: JSON.stringify({ files }) }),
  completeUpload: (id: string, docId: string) =>
    call<ApiDocument>(`/cases/${encodeURIComponent(id)}/documents/${encodeURIComponent(docId)}/complete`, { method: "POST", body: "{}" }),
  /** Close a pending upload the user gave up on, so it no longer holds back the analysis. */
  abandonUpload: (id: string, docId: string) =>
    call<ApiDocument>(`/cases/${encodeURIComponent(id)}/documents/${encodeURIComponent(docId)}/abandon`, { method: "POST", body: "{}" }),
  latestRun: (id: string) => call<RunView>(`/cases/${encodeURIComponent(id)}/runs/latest`),
  /** Every analysis run (report version) of the case, newest first. */
  runs: (id: string) => call<RunSummary[]>(`/cases/${encodeURIComponent(id)}/runs`),
  getRun: (id: string, runId: string) => call<RunView>(`/cases/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}`),
  /** Full analysis by default; `council` re-runs only the council on `sourceRunId` (default: the published version). */
  startRun: (id: string, body: { mode?: RunMode; sourceRunId?: string } = {}) =>
    call<RunView>(`/cases/${encodeURIComponent(id)}/runs`, { method: "POST", body: JSON.stringify(body) }),
  resumeRun: (id: string, runId: string) =>
    call<RunView>(`/cases/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/resume`, { method: "POST", body: "{}" }),
  /** A report section of one version; omit `runId` for the published version. */
  report: <K extends ReportKey>(id: string, section: K, runId?: string) =>
    call<{ runId: string; updatedAt: string; data: ReportData[K] }>(
      `/cases/${encodeURIComponent(id)}/report/${section}${runId ? `?run=${encodeURIComponent(runId)}` : ""}`,
    ),
  /** Council members and their status; `recheck` probes Model Garden again instead of using the cached status. */
  councilModels: (recheck = false) => call<CouncilModels>(`/council/models${recheck ? "?refresh=1" : ""}`),
  asks: (id: string) => call<AskSummary[]>(`/cases/${encodeURIComponent(id)}/asks`),
  getAsk: (id: string, askId: string) => call<AskView>(`/cases/${encodeURIComponent(id)}/asks/${encodeURIComponent(askId)}`),
  createAsk: (id: string, body: AskRequest) =>
    call<AskView>(`/cases/${encodeURIComponent(id)}/asks`, { method: "POST", body: JSON.stringify(body) }),
};

/** True for an ApiError with the given HTTP status. */
export const isStatus = (e: unknown, status: number) => e instanceof ApiError && e.status === status;

/** Only http(s) links from the API are rendered as hrefs; anything else is dropped. */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

/**
 * How an upload failed, which decides what can be done about it:
 * - `transient`: network blip or storage busy. Sending the same file again may work.
 * - `link`: the upload link is no longer usable (expired, rejected). A new link is needed.
 * - `fatal`: the file itself was refused. Retrying cannot help.
 */
export type UploadFailure = "transient" | "link" | "fatal";

export class UploadError extends Error {
  constructor(message: string, public kind: UploadFailure) {
    super(message);
  }
}

// Cloud Storage answers a refused PUT with an XML body such as <Error><Code>ExpiredToken</Code>…</Error>.
const STORAGE_ERRORS: Record<string, [string, UploadFailure]> = {
  ExpiredToken: ["The upload link expired.", "link"],
  SignatureDoesNotMatch: ["Cloud Storage did not accept the upload link.", "link"],
  EntityTooLarge: ["The file is larger than the upload limit.", "fatal"],
  EntityTooSmall: ["The file is empty.", "fatal"],
  AccessDenied: ["Cloud Storage refused the upload.", "fatal"],
};

function storageError(status: number, body: string): UploadError {
  const code = /<Code>([A-Za-z]{1,64})<\/Code>/.exec(body)?.[1] ?? "";
  const known = STORAGE_ERRORS[code];
  if (known) return new UploadError(known[0], known[1]);
  if (status === 408 || status === 429 || status >= 500) return new UploadError(`Cloud Storage is busy (HTTP ${status}).`, "transient");
  return new UploadError(`Cloud Storage refused the upload (HTTP ${status}${code ? `, ${code}` : ""}).`, "fatal");
}

/**
 * PUT a file straight to Cloud Storage through its signed URL (the bytes never touch our servers).
 * Uses XMLHttpRequest because fetch cannot report upload progress.
 */
export function putToSignedUrl(target: UploadTarget, file: File, onProgress?: (sentBytes: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(target.method, target.uploadUrl);
    for (const [name, value] of Object.entries(target.headers)) xhr.setRequestHeader(name, value);
    if (onProgress) xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(storageError(xhr.status, xhr.responseText || "")));
    // A dropped connection and a browser security (CORS) block look the same here: no status, no detail.
    xhr.onerror = () => reject(new UploadError("Could not reach Cloud Storage. Check the connection and retry.", "transient"));
    xhr.onabort = () => reject(new UploadError("The upload was interrupted.", "transient"));
    xhr.send(file);
  });
}

/**
 * Fetch with optional polling. ``intervalMs`` may be a function of the latest
 * data so callers can poll only while something is still running.
 */
export function usePoll<T>(fetcher: (() => Promise<T>) | null, intervalMs: number | ((d: T | undefined) => number | null), deps: unknown[] = []) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  const intervalRef = useRef(intervalMs);
  useEffect(() => {
    fetcherRef.current = fetcher;
    intervalRef.current = intervalMs;
  });
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      const f = fetcherRef.current;
      if (!f) return;
      let latest: T | undefined;
      try {
        latest = await f();
        if (cancelled) return;
        setData(latest);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(e as Error);
      } finally {
        if (!cancelled) setLoading(false);
      }
      const iv = intervalRef.current;
      const ms = typeof iv === "function" ? iv(latest) : iv;
      if (!cancelled && ms) timer = setTimeout(run, document.hidden ? ms * 3 : ms);
    };
    run();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  return { data, error, loading, refresh, setData };
}

export const ACTIVE: CaseStatus[] = ["queued", "ingesting", "ai"];
