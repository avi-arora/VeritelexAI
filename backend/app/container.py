"""Composition root: builds the long-lived clients once per process."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.registry import build_agents
from app.config import Settings
from app.harness.council import CouncilLLM
from app.harness.dag import ASK, PIPELINE
from app.harness.dispatcher import CloudTasksDispatcher, Dispatcher, LocalDispatcher
from app.harness.engine import Orchestrator
from app.harness.llm import GeminiLLM
from app.storage.firestore import Repo
from app.storage.gcs import Gcs


@dataclass
class Container:
    settings: Settings
    repo: Repo
    gcs: Gcs
    dispatcher: Dispatcher
    orchestrator: Orchestrator
    council: CouncilLLM


def build_container(settings: Settings) -> Container:
    repo = Repo(settings)
    gcs = Gcs(settings)
    llm = GeminiLLM(settings)
    council = CouncilLLM(settings, llm)
    dispatcher: Dispatcher
    if settings.dispatcher == "cloud_tasks":
        dispatcher = CloudTasksDispatcher(settings)
    else:
        dispatcher = LocalDispatcher(settings)
    orch = Orchestrator(
        settings=settings, repo=repo, gcs=gcs, llm=llm, dag=PIPELINE, agents=build_agents(), dispatcher=dispatcher,
        council=council, ask_dag=ASK,
    )
    if isinstance(dispatcher, LocalDispatcher):
        dispatcher.handler = orch.execute_step
    return Container(settings, repo, gcs, dispatcher, orch, council)
