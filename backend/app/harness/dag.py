"""Declarative pipeline DAG and pure readiness evaluation.

The DAG is static; *instances* are created at runtime:

* ``fan_out="documents"`` specs get one instance per uploaded document when
  the run starts (``ingest--<docId>``, ``facts--<docId>``).
* ``fan_out="models"`` specs get one instance per council member when the run
  starts (``council--claude``, ``answer--gemini``).
* ``fan_out="issues"`` specs are expanded when the ``issues`` step succeeds,
  one instance per legal issue (``mapping--3``, ``grounding--3``).

Everything in this module is pure (no I/O) so it is exhaustively unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

FanOut = Literal["documents", "models", "issues"]
TERMINAL = frozenset({"succeeded", "failed", "skipped"})
# Fan-outs whose keys are known when the run starts (the rest expand at runtime).
STATIC_FANOUTS = frozenset({"documents", "models"})
# Where each runtime fan-out gets its keys from.
FANOUT_SOURCE: dict[str, str] = {"issues": "issues"}


@dataclass(frozen=True)
class StepSpec:
    name: str
    agent: str
    deps: tuple[str, ...] = ()
    fan_out: FanOut | None = None
    same_key_deps: tuple[str, ...] = ()
    """Deps joined per fan-out key (``facts--d1`` waits only for ``ingest--d1``)."""
    critical: bool = True
    """A failed critical step fails the run; a failed optional step degrades it."""
    timeout_s: int = 900
    max_attempts: int = 4


@dataclass
class Dag:
    specs: list[StepSpec]
    name: str = "analysis"
    by_name: dict[str, StepSpec] = field(init=False)

    def __post_init__(self) -> None:
        self.by_name = {s.name: s for s in self.specs}
        self._validate()

    def _validate(self) -> None:
        seen: set[str] = set()
        for s in self.specs:  # specs must be listed in topological order
            if not s.name.isalpha() or not s.name.islower():
                raise ValueError(f"spec name {s.name!r} must be lowercase letters only (it is part of task ids)")
            missing = [d for d in s.deps if d not in seen]
            if missing:
                raise ValueError(f"{s.name} depends on {missing} which are not declared before it")
            bad = [d for d in s.same_key_deps if d not in s.deps or self.by_name[d].fan_out != s.fan_out]
            if bad:
                raise ValueError(f"{s.name}: same_key_deps {bad} must be deps with the same fan-out")
            seen.add(s.name)

    # ------------------------------------------------------------ instances
    @staticmethod
    def step_id(spec: str, key: str | None) -> str:
        return f"{spec}--{key}" if key is not None else spec

    def initial_steps(self, doc_ids: Iterable[str], models: Iterable[str] = ()) -> tuple[list[dict], list[str]]:
        """Step instances known at run start, and the spec names already materialised."""
        keys = {"documents": list(doc_ids), "models": list(models)}
        steps: list[dict] = []
        materialized: list[str] = []
        for spec in self.specs:
            if spec.fan_out in STATIC_FANOUTS:
                steps += [self.new_step(spec, k) for k in keys[spec.fan_out]]
                materialized.append(spec.name)
            elif spec.fan_out is None:
                steps.append(self.new_step(spec, None))
                materialized.append(spec.name)
        return steps, materialized

    def new_step(self, spec: StepSpec, key: str | None) -> dict:
        deps: list[str] = []
        return {
            "id": self.step_id(spec.name, key),
            "spec": spec.name,
            "key": key,
            "agent": spec.agent,
            "deps": deps,
            "status": "pending",
            "attempts": 0,
            "generation": 0,
            "critical": spec.critical,
            "timeout_s": spec.timeout_s,
            "max_attempts": spec.max_attempts,
        }

    def expand(self, steps: list[dict], materialized: set[str]) -> list[dict]:
        """Materialise runtime fan-outs whose source step has finished."""
        by_id = {s["id"]: s for s in steps}
        created: list[dict] = []
        for spec in self.specs:
            if spec.name in materialized or spec.fan_out is None or spec.fan_out in STATIC_FANOUTS:
                continue
            src = by_id.get(FANOUT_SOURCE[spec.fan_out])
            if src is None or src["status"] not in TERMINAL:
                continue
            keys = [str(k) for k in (src.get("fanout") or [])] if src["status"] == "succeeded" else []
            created += [self.new_step(spec, k) for k in keys]
            materialized.add(spec.name)
        return created

    # ------------------------------------------------------------ readiness
    def evaluate(self, steps: list[dict], materialized: set[str]) -> tuple[list[str], list[str]]:
        """Return (ready_ids, skip_ids) for pending steps, cascading skips to a fixed point.

        Rules for a pending step S and each dep spec D:
          * D not yet materialised             -> wait
          * any relevant D instance not terminal -> wait
          * same-key D instance failed/skipped -> skip S
          * critical D instance failed/skipped -> skip S
          * optional D instance failed         -> S still runs (degraded input)
        """
        status = {s["id"]: s["status"] for s in steps}
        by_spec: dict[str, list[dict]] = {}
        for s in steps:
            by_spec.setdefault(s["spec"], []).append(s)

        ready: list[str] = []
        skipped: list[str] = []
        changed = True
        while changed:
            changed = False
            for s in steps:
                sid = s["id"]
                if status[sid] != "pending" or sid in ready:
                    continue
                verdict = self._verdict(s, by_spec, status, materialized)
                if verdict == "ready":
                    ready.append(sid)
                elif verdict == "skip":
                    status[sid] = "skipped"
                    skipped.append(sid)
                    changed = True
        return ready, skipped

    def _verdict(self, step: dict, by_spec: dict[str, list[dict]], status: dict[str, str], materialized: set[str]) -> str:
        spec = self.by_name[step["spec"]]
        for dep_name in spec.deps:
            if dep_name not in materialized:
                return "wait"
            dep_spec = self.by_name[dep_name]
            if dep_name in spec.same_key_deps:
                instances = [i for i in by_spec.get(dep_name, []) if i["key"] == step["key"]]
            else:
                instances = by_spec.get(dep_name, [])
            states = [status[i["id"]] for i in instances]
            if any(st not in TERMINAL for st in states):
                return "wait"
            if dep_name in spec.same_key_deps and any(st != "succeeded" for st in states):
                return "skip"
            if dep_spec.critical and any(st != "succeeded" for st in states):
                return "skip"
        return "ready"

    def outcome(self, steps: list[dict], materialized: set[str]) -> str | None:
        """Run outcome once every step is terminal and all fan-outs resolved, else None."""
        if any(s["status"] not in TERMINAL for s in steps):
            return None
        if any(sp.name not in materialized for sp in self.specs):
            return None
        if any(s["critical"] and s["status"] != "succeeded" for s in steps):
            return "failed"
        if any(s["status"] != "succeeded" for s in steps):
            return "partial"
        return "succeeded"


PIPELINE = Dag(
    [
        StepSpec("ingest", "ingest", fan_out="documents", critical=False, timeout_s=1500),
        StepSpec("background", "background", deps=("ingest",), timeout_s=900),
        StepSpec("facts", "facts", deps=("ingest",), same_key_deps=("ingest",), fan_out="documents", critical=False, timeout_s=1200),
        StepSpec("chronology", "chronology", deps=("facts",), timeout_s=1500),
        StepSpec("issues", "issues", deps=("chronology",), timeout_s=900),
        StepSpec("mapping", "mapping", deps=("issues",), fan_out="issues", critical=False, timeout_s=900),
        StepSpec("grounding", "grounding", deps=("issues",), fan_out="issues", critical=False, timeout_s=600),
        StepSpec("verify", "verify", deps=("chronology", "mapping"), critical=False, timeout_s=900),
        # Model council: each member reads the record plus the *verified* authorities independently
        # (after verify, so no member can lean on an unverified citation), then the chair compares.
        StepSpec(
            "council", "council", deps=("chronology", "issues", "mapping", "grounding", "verify"), fan_out="models",
            critical=False, timeout_s=900, max_attempts=3,
        ),
        StepSpec("consensus", "consensus", deps=("issues", "council"), critical=False, timeout_s=600, max_attempts=4),
        StepSpec(
            "finalize", "finalize",
            deps=("background", "chronology", "issues", "mapping", "grounding", "verify", "council", "consensus"),
            timeout_s=300, max_attempts=6,
        ),
    ]
)

# "Ask the council": one durable run per question, grounded on a finished report version.
ASK = Dag(
    [
        StepSpec("answer", "answer", fan_out="models", critical=False, timeout_s=600, max_attempts=3),
        # Debate mode: every member reviews the others' answers (waits for all answers); a no-op otherwise.
        StepSpec("review", "review", deps=("answer",), fan_out="models", critical=False, timeout_s=600, max_attempts=3),
        StepSpec("synth", "synth", deps=("answer", "review"), critical=False, timeout_s=480, max_attempts=4),
    ],
    name="ask",
)

# Specs recomputed by a council-only re-run; everything else is reused from the source version.
COUNCIL_REDO = ("council", "consensus", "finalize")
