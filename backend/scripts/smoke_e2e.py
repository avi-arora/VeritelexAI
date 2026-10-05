"""End-to-end smoke test against a running backend (local or deployed).

    uv run python scripts/smoke_e2e.py [--api http://127.0.0.1:8000] [--dir sample_case]

Creates a case, uploads every file in --dir through signed URLs, then polls the
agent run until it finishes and prints the step timeline and report summary.
"""

from __future__ import annotations

import argparse
import mimetypes
import pathlib
import sys
import time

import httpx


def assert_browser_can_put(url: str, headers: dict[str, str], origin: str) -> None:
    """Replay the CORS preflight a browser sends before the PUT.

    Python HTTP clients skip CORS, so without this a bucket policy that blocks browsers passes
    here while every real upload from the web app fails with "Failed to fetch".
    """
    r = httpx.options(url, timeout=30, headers={
        "Origin": origin, "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": ",".join(sorted(h.lower() for h in headers)),
    })
    if r.headers.get("access-control-allow-origin") != origin:
        raise SystemExit(f"CORS preflight from {origin} was refused by the bucket: browser uploads would fail "
                         "(re-run infra/setup.sh to apply the upload CORS policy)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--dir", default=str(pathlib.Path(__file__).resolve().parent.parent / "sample_case"))
    ap.add_argument("--origin", default="http://localhost:3000", help="web app origin the browser uploads from")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    files = sorted(p for p in pathlib.Path(a.dir).iterdir() if p.is_file() and not p.name.startswith("."))
    api = httpx.Client(base_url=f"{a.api.rstrip('/')}/api/v1", timeout=120)

    case = api.post("/cases", json={}).raise_for_status().json()
    cid = case["id"]
    print(f"case {cid} created")
    spec = [{"name": f.name, "size": f.stat().st_size, "contentType": mimetypes.guess_type(f.name)[0] or "application/octet-stream"}
            for f in files]
    targets = api.post(f"/cases/{cid}/uploads", json={"files": spec}).raise_for_status().json()["targets"]
    assert_browser_can_put(targets[0]["uploadUrl"], targets[0]["headers"], a.origin)
    by_name = {f.name: f for f in files}
    for t in targets:
        r = httpx.put(t["uploadUrl"], content=by_name[t["name"]].read_bytes(), headers={**t["headers"], "Origin": a.origin}, timeout=300)
        r.raise_for_status()
        doc = api.post(f"/cases/{cid}/documents/{t['documentId']}/complete").raise_for_status().json()
        print(f"  uploaded {t['name']} -> {doc['status']}")

    start, last = time.time(), ""
    while time.time() - start < a.timeout:
        r = api.get(f"/cases/{cid}/runs/latest")
        if r.status_code == 200:
            run = r.json()
            line = f"[{int(time.time() - start):4d}s] {run['status']:9s} {run['stage']:10s} {run['pct']:3d}% " + " ".join(
                f"{s['id']}={s['status']}" for s in run["steps"] if s["status"] not in ("pending", "succeeded"))
            if line[7:] != last:
                print(line)
                last = line[7:]
            if run["status"] != "running":
                break
        time.sleep(4)
    else:
        print("timed out")
        return 1

    for s in run["steps"]:
        print(f"  {s['id']:28s} {s['status']:9s} attempts={s['attempts']} {s.get('error') or ''}")
    detail = api.get(f"/cases/{cid}").json()
    print(f"\ncase: {detail['no']} | {detail['title']}\n  {detail['type']} | {detail['division']} | status={detail['status']}\n  {detail['note']}")
    for sec in ("background", "matrix", "mapping", "issues", "tools"):
        r = api.get(f"/cases/{cid}/report/{sec}")
        if r.status_code != 200:
            print(f"  {sec}: {r.status_code}")
            continue
        d = r.json()["data"]
        size = {"background": lambda: f"{len(d['paragraphs'])} paragraphs, {len(d['keyFacts'])} key facts",
                "matrix": lambda: f"{len(d['entries'])} dated facts",
                "mapping": lambda: f"{len(d['groups'])} groups, {d['totalDecisions']} decisions ({d['excluded']} excluded)",
                "issues": lambda: f"{len(d['issues'])} issues",
                "tools": lambda: d["sources"]["google"]["meta"]}[sec]()
        print(f"  {sec}: {size}")
    return 0 if run["status"] in ("succeeded", "partial") else 2


if __name__ == "__main__":
    sys.exit(main())
