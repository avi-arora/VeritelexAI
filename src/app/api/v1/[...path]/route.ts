// Backend-for-frontend proxy: the browser calls /api/v1/* on this origin and
// this handler forwards to the private FastAPI service.
//
// * Locally, BACKEND_URL defaults to http://127.0.0.1:8000.
// * On Cloud Run (K_SERVICE is set) the request is authenticated to the private
//   API service with a Google-signed ID token minted by the metadata server for
//   this service's own identity (vtx-web), so the API never needs public access.
//
// TODO(security): no end-user authentication (static login by POC decision).

import type { NextRequest } from "next/server";

const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;
const QUERY_KEYS = new Set(["run", "refresh"]);
const MAX_BODY = 1024 * 1024;

let cachedToken: { value: string; exp: number } | null = null;

async function idToken(): Promise<string | null> {
  if (!process.env.K_SERVICE) return null; // local development: backend is on loopback
  if (cachedToken && cachedToken.exp - 60_000 > Date.now()) return cachedToken.value;
  const url = `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(BACKEND_URL)}`;
  const res = await fetch(url, { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!res.ok) throw new Error(`metadata server returned ${res.status}`);
  const value = await res.text();
  const payload = JSON.parse(Buffer.from(value.split(".")[1], "base64url").toString());
  cachedToken = { value, exp: payload.exp * 1000 };
  return value;
}

async function forward(request: NextRequest, ctx: RouteContext<"/api/v1/[...path]">) {
  const { path } = await ctx.params;
  if (!path.length || path.length > 8 || !path.every((s) => SEGMENT.test(s))) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  // Only known query parameters are forwarded (e.g. ?run= for a report version, ?refresh=1 to re-probe models).
  const query = new URLSearchParams();
  for (const [k, v] of request.nextUrl.searchParams) {
    if (!QUERY_KEYS.has(k)) continue;
    if (!SEGMENT.test(v)) return Response.json({ detail: "Invalid query parameter" }, { status: 400 });
    query.append(k, v);
  }
  const qs = query.toString();
  let body: string | undefined;
  if (request.method !== "GET") {
    body = await request.text();
    if (body.length > MAX_BODY) return Response.json({ detail: "Request too large" }, { status: 413 });
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  try {
    const token = await idToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${BACKEND_URL}/api/v1/${path.join("/")}${qs ? `?${qs}` : ""}`, {
      method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(60_000),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json", "Cache-Control": "no-store" },
    });
  } catch (err) {
    console.error("backend request failed", err instanceof Error ? err.message : err);
    return Response.json({ detail: "The analysis service is unavailable. Try again shortly." }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
