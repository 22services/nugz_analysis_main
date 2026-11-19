"""Registre des huit agents du comite."""
from __future__ import annotations

from app.agents.analysts import (
    DataMarketStateAgent,
    EventCatalystAgent,
    FuturesPositioningAgent,
    MacroAgent,
    TechnicalAgent,
)
from app.agents.base import Agent
from app.agents.decision import CIOAgent, RedTeamAgent, RiskManagerAgent
from app.schemas import AgentCard

# L'ordre est celui du pipeline, pas un ordre d'importance.
AGENTS: list[Agent] = [
    DataMarketStateAgent(),
    TechnicalAgent(),
    MacroAgent(),
    FuturesPositioningAgent(),
    EventCatalystAgent(),
    RedTeamAgent(),
    RiskManagerAgent(),
    CIOAgent(),
]

BY_ID: dict[str, Agent] = {a.id: a for a in AGENTS}

# Les quatre analystes tournent en parallele (fan-out).
ANALYST_IDS = ("technical", "macro", "futures", "event")


def cards() -> list[AgentCard]:
    return [a.card() for a in AGENTS]


def get(agent_id: str) -> Agent:
    return BY_ID[agent_id]
