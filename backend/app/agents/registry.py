"""Agent registry — the engine resolves ``step["agent"]`` through this map."""

from __future__ import annotations

from app.agents.ask import AnswerAgent, ReviewAgent, SynthAgent
from app.agents.background import BackgroundAgent
from app.agents.base import Agent
from app.agents.chronology import ChronologyAgent
from app.agents.council import ConsensusAgent, CouncilMemberAgent
from app.agents.facts import FactsAgent
from app.agents.finalize import FinalizeAgent
from app.agents.grounding import GroundingAgent
from app.agents.ingest import IngestAgent
from app.agents.issues import IssuesAgent
from app.agents.mapping import MappingAgent
from app.agents.verify import VerifyAgent


def build_agents() -> dict[str, Agent]:
    agents: list[Agent] = [
        IngestAgent(), BackgroundAgent(), FactsAgent(), ChronologyAgent(), IssuesAgent(),
        MappingAgent(), GroundingAgent(), VerifyAgent(), CouncilMemberAgent(), ConsensusAgent(), FinalizeAgent(),
        # "Ask the council" runs
        AnswerAgent(), ReviewAgent(), SynthAgent(),
    ]
    return {a.name: a for a in agents}
