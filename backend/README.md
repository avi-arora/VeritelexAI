# VeritelexAI backend

FastAPI service plus the multi-agent harness that analyses an uploaded case record.

> The full architecture lives in the **[project README](../README.md)**. It covers the system diagram, flows, agent DAG, harness design, data model, API, security, GCP resources and IAM, and deployment. This file is the backend quick reference.

## Code map

| Path | Responsibility |
|---|---|
| `app/main.py` | App factory. Mounts `/api/v1` (role `api`/`all`) and `/internal` (role `worker`/`all`), plus middleware: CORS, rate limit, security headers |
| `app/container.py` | Composition root: Firestore repo, GCS, Gemini client, orchestrator, dispatcher, agent registry |
| `app/api/routes.py` | Public REST API (cases, uploads, runs, reports). Upload state machine `pending_upload → uploaded / rejected / abandoned`, the automatic run start, and self-healing on read |
| `app/internal/tasks.py` | Cloud Tasks target; verifies the OIDC token |
| `app/harness/dag.py` | Pipeline definition (`PIPELINE`) and dependency rules |
| `app/harness/engine.py` | Orchestrator: `start_run`, `execute_step`, `advance`, `reconcile`, `retry_failed` |
| `app/harness/dispatcher.py` | `LocalDispatcher` (in-process) / `CloudTasksDispatcher` |
| `app/harness/llm.py` | Gemini wrapper: schema validation and repair, fallback chain, circuit breaker, two-phase Google Search grounding |
| `app/harness/resilience.py` | Retry/backoff, circuit breaker, error types |
| `app/agents/*.py` | `ingest`, `background`, `facts`, `chronology`, `issues`, `mapping`, `grounding`, `verify`, `finalize` |
| `app/agents/registry.py` | Agent name → instance |
| `app/ingest/` | Text extraction from a streamed scratch file on a dedicated parse pool, bounded OCR fallback, file-type sniffing |
| `app/storage/` | Firestore repository (incl. batch creates and compare-and-set status transitions), GCS wrapper (parallel URL signing, streaming downloads, ranged reads, artifacts) |
| `tests/` | `test_dag.py` (graph rules), `test_extract.py` (ingest), `test_units.py` (resilience, file sniffing, citations, formatting), `test_uploads_api.py` (upload API against in-memory fakes: atomic links, guarded transitions, automatic and self-healing start) |

## Pipeline at a glance

```
ingest×doc ─┬─► background ─────────────────────────────────────────────┐
            └─► facts×doc ─► chronology ─► issues ─┬─► mapping×issue  ─┼─► verify ─► finalize
                                                   └─► grounding×issue ┘
```

## Run locally

`--frozen` installs exactly what `uv.lock` pins and never re-resolves against the package index.

```bash
cp .env.example .env
uv sync --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000     # API docs: http://127.0.0.1:8000/docs
```

## Test

```bash
uv run --frozen python -m pytest                       # unit tests (no GCP access needed)
uv run --frozen python scripts/make_sample_case.py     # synthetic case → sample_case/
uv run --frozen python -u scripts/smoke_e2e.py         # browser CORS preflight + full upload + agent run against real GCP
```

To resume a failed or partial run from its checkpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/cases/<caseId>/runs/<runId>/resume
```

## Adding an agent

1. Create `app/agents/<name>.py` with a class that has `name = "<name>"` and `async def run(self, ctx) -> AgentResult`. Read upstream results with `await ctx.outputs("<spec>")`, and call Gemini through `ctx.llm.generate(schema=..., tier=..., search=...)`.
2. Register it in `app/agents/registry.py`.
3. Add a `StepSpec` to `PIPELINE` in `app/harness/dag.py`. Set `deps`, `fan_out` (`documents` or `issues`), `critical` and `timeout_s`. `tests/test_dag.py` validates the graph.
4. If it feeds the UI, add it to `finalize.py`, which builds the report sections.

## Infrastructure

* `infra/setup.sh` sets up the GCP foundation: APIs, Firestore, buckets, queue, Artifact Registry, service accounts and IAM. It is idempotent.
* `infra/deploy.sh` builds with Cloud Build and deploys `vtx-worker`, `vtx-api` and `vtx-web` to Cloud Run. Run it only after everything works locally.
* `infra/cors.sh` (sourced by both) sets the case-files bucket CORS for browser uploads and proves it with live preflights: every listed origin must be allowed with the `Content-Type` and `x-goog-content-length-range` headers, and an unlisted origin must be refused.
