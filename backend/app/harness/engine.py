"""Durable orchestrator.

Execution model (event-driven, checkpointed):

1. ``start_run`` writes the run + initial step instances, then ``advance``.
2. ``advance`` runs in a Firestore transaction: expands runtime fan-outs,
   computes ready/skip sets (pure ``Dag.evaluate``), marks ready steps
   ``queued`` with a new *generation*, and commits. Only after the commit
   are the steps dispatched, so a step is never queued twice for the same
   generation even when many parallel steps finish at once.
3. ``execute_step`` (one delivery of one step) acquires a lease, runs the
   agent under a timeout with a heartbeat, checkpoints the output to GCS,
   marks the step terminal and calls ``advance`` again.
4. Failures: retryable errors re-raise so the dispatcher (Cloud Tasks or
   local) redelivers with backoff; after ``max_attempts`` or on permanent
   errors the step is marked ``failed`` and the DAG decides whether to
   skip dependants (critical) or continue degraded (optional).
5. ``reconcile`` re-dispatches steps stranded by a crash (expired lease or
   queued for too long) — the run resumes from its last checkpoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import uuid
from datetime import timedelta
from typing import Any

from google.api_core import exceptions as gexc
from google.cloud import firestore

from app.agents.base import Agent, AgentContext
from app.config import Settings
from app.harness.dag import ASK, COUNCIL_REDO, FANOUT_SOURCE, TERMINAL, Dag
from app.harness.dispatcher import Dispatcher
from app.harness.llm import LLM
from app.harness.resilience import (
    LeaseHeldError,
    PermanentStepError,
    RetryableStepError,
    backoff_delay,
    is_retryable,
)
from app.logging_setup import get_logger, log_context
from app.storage.firestore import Repo, now
from app.storage.gcs import Gcs

log = get_logger(__name__)

STAGE_NOTES = {
    "background": "Extracting the case background",
    "facts": "Extracting dates and facts",
    "chronology": "Building the chronology",
    "issues": "Identifying the legal issues",
    "mapping": "Mapping facts to decided cases",
    "grounding": "Grounding the issues with Google Search",
    "verify": "Verifying every citation",
    "council": "The model council is reading the record",
    "consensus": "Comparing the council's readings",
    "finalize": "Assembling the report",
}
# Firestore batches hold at most 500 writes.
_BATCH_LIMIT = 450
_CHUNK = 400


class Orchestrator:
    def __init__(
        self, *, settings: Settings, repo: Repo, gcs: Gcs, llm: LLM, dag: Dag, agents: dict[str, Agent],
        dispatcher: Dispatcher, council: Any = None, ask_dag: Dag | None = None,
    ):
        self.s = settings
        self.repo = repo
        self.gcs = gcs
        self.llm = llm
        self.dag = dag
        self.ask_dag = ask_dag or ASK
        self.council = council
        self.agents = agents
        self.dispatcher = dispatcher
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"

    def dag_for(self, run_id: str) -> Dag:
        """Ask runs ("q…") use the ask DAG; analysis runs ("r…") the report pipeline."""
        return self.ask_dag if run_id.startswith("q") else self.dag

    def council_ids(self) -> list[str]:
        return list(self.council.ids()) if self.council is not None else []

    # ================================================================ runs
    async def start_run(
        self, case_id: str, *, trigger: str, idem_key: str | None = None,
        mode: str = "full", source_run_id: str | None = None,
    ) -> str:
        """Start a new report version.

        ``mode="full"`` analyses the case's current documents from scratch. ``mode="council"``
        reuses every finished step of ``source_run_id`` (default: the published version) and only
        recomputes the council, the consensus and the report assembly.
        """
        if idem_key:
            existing = await self.repo.find_run_by_key(case_id, idem_key)
            if existing:
                log.info("run for key %s already exists: %s", idem_key, existing["id"])
                return existing["id"]
        members = self.council_ids()
        ts = now()
        if mode == "council":
            steps, materialized, doc_ids, source_run_id = await self._council_rerun_steps(case_id, source_run_id, members)
            trigger = "council"
        else:
            docs = [d for d in await self.repo.list_documents(case_id) if d.get("status") in ("uploaded", "ingested", "unreadable")]
            if not docs:
                raise PermanentStepError("No uploaded documents to analyse", "Upload at least one document first")
            doc_ids = [d["id"] for d in docs]
            steps, materialized = self.dag.initial_steps(doc_ids, members)
            source_run_id = None

        # A key-derived id + create() makes concurrent starts for the same key collapse into one run.
        run_id = "r" + (hashlib.sha256(f"{case_id}:{idem_key}".encode()).hexdigest()[:12] if idem_key else uuid.uuid4().hex[:12])
        run_doc = {
            "status": "running", "trigger": trigger, "idem_key": idem_key, "doc_ids": doc_ids,
            "materialized": materialized, "created_at": ts, "updated_at": ts, "stage": "queued", "pct": 0,
            "dag": self.dag.name, "mode": mode, "council_models": members, "source_run_id": source_run_id,
        }
        try:
            await self._write_run(case_id, run_id, run_doc, steps, ts)
        except gexc.AlreadyExists:
            log.info("run %s already created by a concurrent request", run_id)
            return run_id
        await self.repo.update_case(case_id, {
            "latest_run_id": run_id, "status": "ai" if mode == "council" else "queued", "pct": 0, "at": None,
            "note": "Re-running the model council" if mode == "council" else "Waiting for a processing slot",
        })
        log.info("run %s started for case %s with %d documents (%s, %s)", run_id, case_id, len(doc_ids), trigger, mode)
        await self.advance(case_id, run_id)
        return run_id

    async def _council_rerun_steps(
        self, case_id: str, source_run_id: str | None, members: list[str],
    ) -> tuple[list[dict], list[str], list[str], str]:
        if not source_run_id:
            case = await self.repo.get_case(case_id) or {}
            source_run_id = case.get("report_run_id") or await self.repo.legacy_report_run(case_id)
        src = await self.repo.get_run(case_id, source_run_id) if source_run_id and source_run_id.startswith("r") else None
        if not src:
            raise PermanentStepError(
                f"no source version for a council re-run ({source_run_id})",
                "There is no finished analysis to re-run the council on. Run a full analysis first.",
            )
        if src.get("status") not in ("succeeded", "partial"):
            raise PermanentStepError(
                f"source run {source_run_id} is {src.get('status')}",
                "That version did not finish, so the council cannot be re-run on it. Run a full analysis instead.",
            )
        src_steps = await self.repo.list_steps(case_id, source_run_id)
        if not any(s["spec"] == "issues" and s["status"] == "succeeded" for s in src_steps):
            raise PermanentStepError(
                f"source run {source_run_id} has no issues output",
                "That version has no legal issues for the council to read. Run a full analysis instead.",
            )
        # Finished steps are copied as-is: their outputs stay where they are in GCS (immutable), and
        # a failed optional step stays failed, so the new version is honest about the same gaps.
        drop = {"lease_owner", "lease_until", "queued_at", "created_at", "updated_at"}
        steps = [
            {k: v for k, v in s.items() if k not in drop} | {"reused_from": source_run_id}
            for s in src_steps
            if s["spec"] not in COUNCIL_REDO and s["spec"] in self.dag.by_name and s["status"] in TERMINAL
        ]
        for spec in self.dag.specs:
            if spec.name in COUNCIL_REDO:
                keys: list[str | None] = list(members) if spec.fan_out == "models" else [None]
                steps += [self.dag.new_step(spec, k) for k in keys]
        return steps, [sp.name for sp in self.dag.specs], list(src.get("doc_ids") or []), source_run_id

    async def start_ask(
        self, case_id: str, *, question: str, mode: str, scope: dict[str, Any], members: list[str], source_run_id: str,
        source_version: int | None = None,
    ) -> str:
        """Start an "ask the council" run: a durable mini-run on the same engine (leases, retries, recovery)."""
        ask_id = "q" + uuid.uuid4().hex[:12]
        steps, materialized = self.ask_dag.initial_steps([], members)
        ts = now()
        await self._write_run(case_id, ask_id, {
            "dag": self.ask_dag.name, "trigger": "ask", "status": "running", "question": question, "mode": mode,
            "scope": scope, "council_models": list(members), "source_run_id": source_run_id,
            "source_version": source_version, "doc_ids": [],
            "materialized": materialized, "created_at": ts, "updated_at": ts, "stage": "queued", "pct": 0,
        }, steps, ts)
        log.info("ask %s started for case %s (%s, %d members)", ask_id, case_id, mode, len(members))
        await self.advance(case_id, ask_id)
        return ask_id

    async def _write_run(self, case_id: str, run_id: str, run_doc: dict[str, Any], steps: list[dict], ts: Any) -> None:
        run_ref = self.repo.run_ref(case_id, run_id)
        writes = [
            (self.repo.step_ref(case_id, run_id, st["id"]), {k: v for k, v in st.items() if k != "id"} | {"created_at": ts, "updated_at": ts})
            for st in steps
        ]
        if len(writes) < _BATCH_LIMIT:
            batch = self.repo.db.batch()
            batch.create(run_ref, run_doc)
            for ref, data in writes:
                batch.set(ref, data)
            await batch.commit()
            return
        # Too many steps for one batch: write them in chunks, then create the run doc last as the
        # commit point. Steps orphaned by a crash before that are inert (nothing dispatches them).
        if (await run_ref.get()).exists:
            raise gexc.AlreadyExists(f"run {run_id} exists")
        for i in range(0, len(writes), _CHUNK):
            batch = self.repo.db.batch()
            for ref, data in writes[i:i + _CHUNK]:
                batch.set(ref, data)
            await batch.commit()
        await run_ref.create(run_doc)

    async def retry_failed(self, case_id: str, run_id: str) -> int:
        """Resume a failed run from its checkpoints: succeeded steps keep their outputs,
        failed and skipped steps are reset and the DAG is re-evaluated."""
        repo, dag = self.repo, self.dag_for(run_id)

        @firestore.async_transactional
        async def txn(transaction: Any) -> int:
            run = (await repo.run_ref(case_id, run_id).get(transaction=transaction)).to_dict() or {}
            if run.get("status") not in ("failed", "partial"):
                return 0
            steps = await repo.list_steps(case_id, run_id, transaction)
            reset = [s for s in steps if s["status"] in ("failed", "skipped")]
            # Anything downstream of a reset step must be recomputed too (e.g. finalize after a partial run).
            redo = {s["spec"] for s in reset}
            changed = True
            while changed:
                changed = False
                for sp in dag.specs:
                    if sp.name not in redo and any(d in redo for d in sp.deps):
                        redo.add(sp.name)
                        changed = True
            ts = now()
            n = 0
            for s in steps:
                if s["status"] in ("failed", "skipped") or (s["spec"] in redo and s["spec"] not in {r["spec"] for r in reset}):
                    transaction.update(repo.step_ref(case_id, run_id, s["id"]), {
                        "status": "pending", "attempts": 0, "error": None, "user_error": None, "outcome": None,
                        "lease_owner": None, "lease_until": None, "finished_at": None, "updated_at": ts,
                    })
                    n += 1
            # Runtime fan-outs whose source failed were materialised with zero instances:
            # un-materialise them so they expand again once the source succeeds.
            reset_specs = {r["spec"] for r in reset}
            materialized = [
                m for m in run.get("materialized", [])
                if not (m in dag.by_name and dag.by_name[m].fan_out in FANOUT_SOURCE and FANOUT_SOURCE[dag.by_name[m].fan_out] in reset_specs)
            ]
            transaction.update(repo.run_ref(case_id, run_id), {
                "status": "running", "finished_at": None, "updated_at": ts, "materialized": materialized,
            })
            return n

        n = await txn(repo.transaction())
        if n:
            if not run_id.startswith("q"):  # asks never own the case status
                await repo.update_case(case_id, {"latest_run_id": run_id, "status": "ai", "at": None, "note": "Resuming the analysis"})
            await self.advance(case_id, run_id)
        return n

    async def advance(self, case_id: str, run_id: str) -> str | None:
        repo, dag = self.repo, self.dag_for(run_id)

        @firestore.async_transactional
        async def txn(transaction: Any) -> tuple[list[tuple[str, int]], str | None, list[dict], dict]:
            run_snap = await repo.run_ref(case_id, run_id).get(transaction=transaction)
            run = run_snap.to_dict()
            steps = await repo.list_steps(case_id, run_id, transaction)
            materialized = set(run.get("materialized", []))
            ts = now()

            created = dag.expand(steps, materialized)
            for st in created:
                transaction.create(repo.step_ref(case_id, run_id, st["id"]), {k: v for k, v in st.items() if k != "id"} | {"created_at": ts})
            steps = steps + created

            ready, skipped = dag.evaluate(steps, materialized)
            by_id = {s["id"]: s for s in steps}
            for sid in skipped:
                by_id[sid]["status"] = "skipped"
                transaction.update(repo.step_ref(case_id, run_id, sid), {
                    "status": "skipped", "finished_at": ts, "updated_at": ts,
                    "error": "Skipped because a required upstream step did not succeed",
                })
            dispatches: list[tuple[str, int]] = []
            for sid in ready:
                gen = int(by_id[sid].get("generation", 0)) + 1
                by_id[sid].update(status="queued", generation=gen)
                transaction.update(repo.step_ref(case_id, run_id, sid), {
                    "status": "queued", "generation": gen, "queued_at": ts, "updated_at": ts,
                })
                dispatches.append((sid, gen))

            outcome = dag.outcome(steps, materialized)
            stage, pct = _progress(steps)
            run_update: dict[str, Any] = {"materialized": sorted(materialized), "updated_at": ts, "stage": stage, "pct": pct}
            if outcome and run.get("status") == "running":
                run_update |= {"status": outcome, "finished_at": ts, "stage": "done", "pct": 100}
            transaction.update(repo.run_ref(case_id, run_id), run_update)
            return dispatches, (outcome if run.get("status") == "running" else None), steps, run

        # Parallel steps finishing together contend on the same run; Firestore aborts the
        # losers (sometimes already on the in-transaction read, which the SDK does not retry).
        for attempt in range(1, 9):
            try:
                dispatches, outcome, steps, run = await txn(repo.transaction())
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 8 or not is_retryable(exc):
                    raise
                delay = backoff_delay(attempt, base=0.2, cap=5.0)
                log.info("advance contention on run %s (attempt %d), retrying in %.2fs", run_id, attempt, delay)
                await asyncio.sleep(delay)
        for sid, gen in dispatches:
            try:
                await self.dispatcher.dispatch(case_id, run_id, sid, gen)
            except Exception:  # noqa: BLE001 - reconcile() will pick the step up again
                log.exception("dispatch of %s failed; it will be reconciled", sid)
        await self._sync_case(case_id, run_id, steps, outcome)
        return outcome

    async def _sync_case(self, case_id: str, run_id: str, steps: list[dict], outcome: str | None) -> None:
        if run_id.startswith("q"):
            return  # asks never own the case status
        case = await self.repo.get_case(case_id)
        if not case or case.get("latest_run_id") != run_id:
            return  # a newer run owns the case status
        if outcome == "failed":
            failed = next((s for s in steps if s["critical"] and s["status"] == "failed"), None)
            failed = failed or next((s for s in steps if s["status"] == "failed"), None)
            note = (failed or {}).get("user_error") or "Analysis could not be completed"
            if case.get("report_run_id") or case.get("report_ready_at"):
                # A re-run failed but an earlier version is published: keep that report readable.
                await self.repo.update_case(case_id, {
                    "status": "ready", "at": None, "pct": 100,
                    "note": f"The latest re-run did not finish ({note}). Showing the previous version.",
                })
                return
            stage_at = 2 if failed and failed["spec"] == "ingest" else 3
            await self.repo.update_case(case_id, {"status": "action", "at": stage_at, "pct": None, "note": note})
            return
        if outcome:  # succeeded / partial: finalize has already published and set status
            return
        stage, pct = _progress(steps)
        if stage == "ingesting":
            ingest = [s for s in steps if s["spec"] == "ingest"]
            done = sum(s["status"] in TERMINAL for s in ingest)
            note = f"Reading documents · {done} of {len(ingest)} documents"
        else:
            running = [s["spec"] for s in steps if s["status"] in ("queued", "running", "retrying")]
            spec = next((sp.name for sp in self.dag.specs if sp.name in running), None)
            note = STAGE_NOTES.get(spec or "", "Analysis running")
        if case.get("status") != stage or case.get("pct") != pct or case.get("note") != note:
            await self.repo.update_case(case_id, {"status": stage, "pct": pct, "note": note, "at": None})

    # ================================================================ steps
    async def execute_step(self, case_id: str, run_id: str, step_id: str, generation: int) -> str:
        with log_context(case_id=case_id, run_id=run_id, step_id=step_id):
            step = await self._acquire(case_id, run_id, step_id, generation)
            if step is None:
                # Duplicate / late delivery. Advancing is idempotent and heals the case where a
                # previous delivery recorded the result but crashed before advancing the DAG.
                await self.advance(case_id, run_id)
                return "noop"
            spec = self.dag_for(run_id).by_name[step["spec"]]
            agent = self.agents[step["agent"]]
            ctx = AgentContext(case_id, run_id, step, self.repo, self.gcs, self.llm, self.s, council=self.council)
            heartbeat = asyncio.create_task(self._heartbeat(case_id, run_id, step_id))
            try:
                with log_context(agent=step["agent"], attempt=step["attempts"]):
                    log.info("step started")
                    result = await asyncio.wait_for(agent.run(ctx), timeout=spec.timeout_s)
                    uri = await self.gcs.write_json(f"cases/{case_id}/runs/{run_id}/{step_id}.json", result.output)
                    await self.repo.update_step(case_id, run_id, step_id, {
                        "status": "succeeded", "output_uri": uri, "fanout": result.fanout, "finished_at": now(),
                        "lease_owner": None, "lease_until": None, "error": None, "user_error": None,
                        "usage": ctx.usage, "models": sorted(ctx.models), "outcome": result.outcome,
                    })
                    log.info("step succeeded", extra={"fields": {"usage": ctx.usage}})
            except Exception as exc:  # noqa: BLE001
                await self._on_failure(case_id, run_id, step, exc)
            finally:
                heartbeat.cancel()
            await self.advance(case_id, run_id)
            return "done"

    async def _on_failure(self, case_id: str, run_id: str, step: dict, exc: BaseException) -> None:
        if isinstance(exc, asyncio.TimeoutError):
            exc = RetryableStepError(f"step timed out after {step['timeout_s']}s", "An analysis step timed out")
        retryable = is_retryable(exc)
        user_error = getattr(exc, "user_message", None) or "An analysis step failed"
        detail = f"{type(exc).__name__}: {exc}"[:2000]
        if retryable and step["attempts"] < step["max_attempts"]:
            log.warning("step attempt %d/%d failed (retryable): %s", step["attempts"], step["max_attempts"], detail)
            await self.repo.update_step(case_id, run_id, step["id"], {
                "status": "retrying", "error": detail, "user_error": user_error, "lease_owner": None, "lease_until": None,
            })
            raise RetryableStepError(detail, user_error) from exc
        log.error("step failed permanently after %d attempts: %s", step["attempts"], detail, exc_info=exc)
        await self.repo.update_step(case_id, run_id, step["id"], {
            "status": "failed", "error": detail, "user_error": user_error, "finished_at": now(),
            "lease_owner": None, "lease_until": None,
        })

    async def _acquire(self, case_id: str, run_id: str, step_id: str, generation: int) -> dict | None:
        ref = self.repo.step_ref(case_id, run_id, step_id)
        worker, lease_s = self.worker_id, self.s.lease_seconds

        @firestore.async_transactional
        async def txn(transaction: Any) -> tuple[dict | None, bool]:
            snap = await ref.get(transaction=transaction)
            if not snap.exists:
                return None, False
            st = {"id": snap.id, **snap.to_dict()}
            ts = now()
            if st["status"] in TERMINAL or st["status"] == "pending":
                return None, False
            if generation < int(st.get("generation", 0)):
                return None, False  # superseded by a newer dispatch
            lease_until = st.get("lease_until")
            if st["status"] == "running" and lease_until and lease_until > ts and st.get("lease_owner") != worker:
                raise LeaseHeldError(step_id)
            if st["attempts"] >= st["max_attempts"]:
                # The previous attempt crashed the worker without recording a result.
                transaction.update(ref, {
                    "status": "failed", "finished_at": ts, "updated_at": ts, "lease_owner": None,
                    "error": st.get("error") or "Worker lost during the final attempt",
                    "user_error": st.get("user_error") or "An analysis step could not complete",
                })
                return None, True
            st["attempts"] += 1
            transaction.update(ref, {
                "status": "running", "attempts": st["attempts"], "lease_owner": worker,
                "lease_until": ts + timedelta(seconds=lease_s), "started_at": st.get("started_at") or ts, "updated_at": ts,
            })
            return st, False

        step, needs_advance = await txn(self.repo.transaction())
        if needs_advance:
            await self.advance(case_id, run_id)
        return step

    async def _heartbeat(self, case_id: str, run_id: str, step_id: str) -> None:
        interval = max(5, self.s.lease_seconds // 3)
        try:
            while True:
                await asyncio.sleep(interval)
                await self.repo.update_step(case_id, run_id, step_id, {
                    "lease_until": now() + timedelta(seconds=self.s.lease_seconds),
                })
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - a missed heartbeat only risks a duplicate (idempotent) attempt
            log.warning("heartbeat failed for %s", step_id, exc_info=True)

    # ================================================================ recovery
    async def reconcile(self, case_id: str, run_id: str, *, force: bool = False) -> int:
        """Re-dispatch steps stranded by a crash or a lost dispatch. Returns the number re-dispatched."""
        run = await self.repo.get_run(case_id, run_id)
        if not run or run.get("status") != "running":
            return 0
        steps = await self.repo.list_steps(case_id, run_id)
        ts = now()
        stale = timedelta(seconds=self.s.stale_run_seconds)
        redo: list[dict] = []
        for st in steps:
            if st["status"] == "running" and (not st.get("lease_until") or st["lease_until"] < ts):
                redo.append(st)
            elif st["status"] in ("queued", "retrying") and (force or (st.get("updated_at") and ts - st["updated_at"] > stale)):
                redo.append(st)
        for st in redo:
            gen = int(st.get("generation", 0)) + 1
            await self.repo.update_step(case_id, run_id, st["id"], {"status": "queued", "generation": gen, "queued_at": ts})
            await self.dispatcher.dispatch(case_id, run_id, st["id"], gen)
        if redo:
            log.warning("reconciled %d stranded steps in run %s", len(redo), run_id)
        await self.advance(case_id, run_id)
        return len(redo)

    async def resume_active_runs(self) -> None:
        """Local mode: after a restart, in-memory deliveries are gone — resume every active run and ask."""
        for case in await self.repo.list_cases():
            if case.get("status") in ("queued", "ingesting", "ai") and case.get("latest_run_id"):
                try:
                    await self.reconcile(case["id"], case["latest_run_id"], force=True)
                except Exception:  # noqa: BLE001
                    log.exception("could not resume run %s", case["latest_run_id"])
            try:
                for ask in await self.repo.running_asks(case["id"]):
                    await self.reconcile(case["id"], ask["id"], force=True)
            except Exception:  # noqa: BLE001
                log.exception("could not resume the asks of case %s", case["id"])


def _progress(steps: list[dict]) -> tuple[str, int]:
    ingest = [s for s in steps if s["spec"] == "ingest"]
    if ingest and any(s["status"] not in TERMINAL for s in ingest):
        done = sum(s["status"] in TERMINAL for s in ingest)
        if done == 0 and all(s["status"] in ("pending", "queued") for s in ingest):
            return "queued" if all(s["status"] == "pending" for s in ingest) else "ingesting", 0
        return "ingesting", int(100 * done / len(ingest))
    rest = [s for s in steps if s["spec"] != "ingest"]
    if not rest:
        return "ai", 0
    done = sum(s["status"] in TERMINAL for s in rest)
    return "ai", min(99, int(100 * done / len(rest)))
