// Date and duration formatting for the report screens (en-GB, e.g. "03 Oct 2026, 14:31").
// Only call these with data fetched on the client, so server and client render the same text.

const valid = (iso: string | null | undefined): iso is string => !!iso && Number.isFinite(Date.parse(iso));

export const fmtDate = (iso: string | null | undefined) =>
  valid(iso) ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "";

export const fmtDateTime = (iso: string | null | undefined) =>
  valid(iso) ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "";

/** "41 seconds", "3 min 5 s", "1 h 12 min". */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "";
  const s = Math.round(seconds);
  if (s < 60) return `${s} ${s === 1 ? "second" : "seconds"}`;
  if (s < 3600) return `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ""}`;
  const m = Math.round(s / 60);
  return `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
}

/** Seconds between two ISO timestamps, or null when either is missing (no clock reads, so it is safe in render). */
export function secondsBetween(startIso: string | null | undefined, endIso: string | null | undefined): number | null {
  if (!valid(startIso) || !valid(endIso)) return null;
  return Math.max(0, (Date.parse(endIso) - Date.parse(startIso)) / 1000);
}
