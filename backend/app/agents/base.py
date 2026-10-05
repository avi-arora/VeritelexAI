"""Agent contract shared by every agent and the engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.harness.llm import LLM, LLMResult
from app.storage.firestore import Repo
from app.storage.gcs import Gcs

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


@dataclass
class AgentResult:
    output: dict[str, Any]
    fanout: list[str] | None = None
    outcome: str | None = None
    """Short machine-readable result stored on the step (e.g. ``unavailable``, ``skipped``)."""


@dataclass
class AgentContext:
    case_id: str
    run_id: str
    step: dict[str, Any]
    repo: Repo
    gcs: Gcs
    llm: LLM
    settings: Settings
    council: Any = None
    """``CouncilLLM`` for council and ask agents."""
    usage: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "output": 0, "total": 0, "calls": 0})
    models: set[str] = field(default_factory=set)
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    _steps: list[dict[str, Any]] | None = None
    _run_steps: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def key(self) -> str | None:
        return self.step.get("key")

    def track(self, res: LLMResult[Any]) -> None:
        for k in ("prompt", "output", "total"):
            self.usage[k] += res.usage.get(k, 0)
        self.usage["calls"] += 1
        self.models.add(res.model)

    async def outputs(self, spec: str) -> dict[str, dict[str, Any]]:
        """Outputs of every *succeeded* instance of an upstream spec, keyed by fan-out key
        (``"_"`` for singletons). Only ancestors are guaranteed to be terminal."""
        return await self.outputs_for(self.run_id, spec)

    async def outputs_for(self, run_id: str, spec: str) -> dict[str, dict[str, Any]]:
        """Like :meth:`outputs`, for any run of this case (e.g. the report version an ask is grounded on)."""
        ck = spec if run_id == self.run_id else f"{run_id}:{spec}"
        if ck in self._cache:
            return self._cache[ck]
        steps = await self._list(run_id)
        done = [s for s in steps if s["spec"] == spec and s["status"] == "succeeded" and s.get("output_uri")]
        datas = await asyncio.gather(*(self.gcs.read_json(s["output_uri"]) for s in done))
        out = {(s.get("key") or "_"): d for s, d in zip(done, datas, strict=True)}
        self._cache[ck] = out
        return out

    async def step_states(self, spec: str, run_id: str | None = None) -> list[dict[str, Any]]:
        """Step records (any status) of a spec, e.g. to report why a council member failed."""
        return [s for s in await self._list(run_id or self.run_id) if s["spec"] == spec]

    async def _list(self, run_id: str) -> list[dict[str, Any]]:
        if run_id == self.run_id:
            if self._steps is None:
                self._steps = await self.repo.list_steps(self.case_id, self.run_id)
            return self._steps
        if run_id not in self._run_steps:
            self._run_steps[run_id] = await self.repo.list_steps(self.case_id, run_id)
        return self._run_steps[run_id]

    async def output(self, spec: str) -> dict[str, Any] | None:
        return (await self.outputs(spec)).get("_")

    async def output_of(self, spec: str, key: str) -> dict[str, Any] | None:
        """Output of one specific upstream instance (e.g. ``ingest--<docId>``)."""
        st = await self.repo.get_step(self.case_id, self.run_id, f"{spec}--{key}")
        if not st or st.get("status") != "succeeded" or not st.get("output_uri"):
            return None
        return await self.gcs.read_json(st["output_uri"])


class Agent(Protocol):
    name: str

    async def run(self, ctx: AgentContext) -> AgentResult: ...
