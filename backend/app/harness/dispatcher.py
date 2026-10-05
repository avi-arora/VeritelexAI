"""Step dispatchers.

* ``LocalDispatcher`` — in-process asyncio execution with bounded concurrency
  and backoff retries. Used for local development and tests.
* ``CloudTasksDispatcher`` — durable at-least-once delivery through Cloud
  Tasks to the worker's ``/internal/tasks/execute`` endpoint with an OIDC
  token. Task names are deterministic (run/step/generation) so a duplicate
  dispatch is de-duplicated by Cloud Tasks.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Awaitable, Callable, Protocol

from google.api_core import exceptions as gexc
from google.cloud import tasks_v2
from google.protobuf import duration_pb2

from app.config import Settings
from app.harness.resilience import LeaseHeldError, RetryableStepError, backoff_delay, is_retryable
from app.logging_setup import get_logger

log = get_logger(__name__)
Handler = Callable[[str, str, str, int], Awaitable[object]]


class Dispatcher(Protocol):
    async def dispatch(self, case_id: str, run_id: str, step_id: str, generation: int) -> None: ...


class LocalDispatcher:
    MAX_DELIVERIES = 12

    def __init__(self, settings: Settings):
        self._sem = asyncio.Semaphore(settings.local_concurrency)
        self._tasks: set[asyncio.Task] = set()
        self.handler: Handler | None = None

    async def dispatch(self, case_id: str, run_id: str, step_id: str, generation: int) -> None:
        task = asyncio.create_task(self._deliver(case_id, run_id, step_id, generation), name=f"{run_id}/{step_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, case_id: str, run_id: str, step_id: str, generation: int) -> None:
        assert self.handler is not None, "LocalDispatcher.handler not wired"
        for delivery in range(1, self.MAX_DELIVERIES + 1):
            async with self._sem:
                try:
                    await self.handler(case_id, run_id, step_id, generation)
                    return
                except LeaseHeldError:
                    delay = 15.0
                except RetryableStepError as exc:
                    delay = backoff_delay(delivery, base=5, cap=120)
                    log.info("step %s will be redelivered in %.0fs (%s)", step_id, delay, exc)
                except Exception as exc:  # noqa: BLE001
                    if not is_retryable(exc):  # engine has already recorded the failure
                        log.exception("step %s delivery crashed", step_id)
                        return
                    # Infrastructure hiccup (e.g. Firestore contention): redeliver, like Cloud Tasks would.
                    delay = backoff_delay(delivery, base=2, cap=60)
                    log.warning("step %s delivery hit a transient error, redelivering in %.0fs: %s", step_id, delay, exc)
            await asyncio.sleep(delay)
        log.error("step %s exhausted local deliveries", step_id)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


_TASK_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]")


class CloudTasksDispatcher:
    def __init__(self, settings: Settings):
        if not settings.worker_url or not settings.tasks_invoker_sa:
            raise RuntimeError("VTX_WORKER_URL and VTX_TASKS_INVOKER_SA are required for cloud_tasks dispatch")
        self._s = settings
        self._client = tasks_v2.CloudTasksAsyncClient()
        self._parent = self._client.queue_path(settings.project_id, settings.region, settings.tasks_queue)

    async def dispatch(self, case_id: str, run_id: str, step_id: str, generation: int) -> None:
        name = _TASK_NAME_SAFE.sub("_", f"{case_id}-{run_id}-{step_id}-g{generation}")[:480]
        body = json.dumps({"caseId": case_id, "runId": run_id, "stepId": step_id, "generation": generation}).encode()
        task = tasks_v2.Task(
            name=f"{self._parent}/tasks/{name}",
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{self._s.worker_url.rstrip('/')}/internal/tasks/execute",
                headers={"Content-Type": "application/json"},
                body=body,
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=self._s.tasks_invoker_sa, audience=self._s.worker_url.rstrip("/")
                ),
            ),
            dispatch_deadline=duration_pb2.Duration(seconds=1800),
        )
        try:
            await self._client.create_task(parent=self._parent, task=task)
        except gexc.AlreadyExists:
            log.info("task %s already enqueued (deduplicated)", name)
