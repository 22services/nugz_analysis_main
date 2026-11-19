"""
Socle commun des agents du comite.

En V1 aucun agent n'est branche a ses outils: `ToolSpec.connected = False`
partout. Les contrats, le mandat, l'orchestration et l'UI sont reels; les
feeds de donnees et les appels LLM sont simules. C'est volontaire - on valide
la structure de decision avant de payer des donnees de marche.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas import (
    AgentCard,
    AgentOutput,
    AgentStatus,
    FeatureVector,
    Localized,
    ModelTier,
    RunStage,
    ToolSpec,
    TriggerCandidate,
)


@dataclass
class RunContext:
    """Tout ce qu'un agent a le droit de lire pendant un run."""
    run_id: str
    trigger: TriggerCandidate
    features: FeatureVector
    market: dict                                  # sortie de la couche deterministe
    outputs: dict[str, AgentOutput] = field(default_factory=dict)
    halted: bool = False
    halt_reason: Localized | None = None

    def get(self, agent_id: str) -> AgentOutput | None:
        return self.outputs.get(agent_id)

    def payload(self, agent_id: str) -> dict:
        out = self.outputs.get(agent_id)
        return out.payload if out else {}


class Agent(ABC):
    """Un agent = un mandat, un contrat de sortie, une place dans le pipeline."""

    id: str
    order: int
    stage: RunStage
    model_tier: ModelTier = ModelTier.CHEAP
    can_veto: bool = False

    name: Localized
    role: Localized
    mandate: Localized
    plain: Localized                              # version comprehensible sans jargon
    tools: list[ToolSpec] = []

    # ------------------------------------------------------------------
    @property
    def is_llm(self) -> bool:
        return self.model_tier is not ModelTier.NONE

    @property
    def model_hint(self) -> str:
        return {
            ModelTier.NONE: "Python deterministe - aucun LLM",
            ModelTier.CHEAP: "Modele economique, sortie contrainte par schema",
            ModelTier.STRONG: "Modele de raisonnement",
        }[self.model_tier]

    def card(self) -> AgentCard:
        return AgentCard(
            id=self.id,
            order=self.order,
            name=self.name,
            role=self.role,
            mandate=self.mandate,
            plain=self.plain,
            can_veto=self.can_veto,
            tools=self.tools,
            model_hint=self.model_hint,
            stage=self.stage,
        )

    # ------------------------------------------------------------------
    async def execute(self, ctx: RunContext) -> AgentOutput:
        """Enveloppe commune: horodatage, duree, gestion d'echec."""
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()

        if ctx.halted and self.id != "data_market_state":
            return AgentOutput(
                agent_id=self.id,
                status=AgentStatus.BLOCKED,
                started_at=started,
                finished_at=started,
                duration_ms=0,
                headline=ctx.halt_reason,
            )

        try:
            out = await self.run(ctx)
        except Exception as exc:  # fail-closed: un agent mort ne vote pas
            out = AgentOutput(
                agent_id=self.id,
                status=AgentStatus.FAILED,
                headline=Localized(
                    fr=f"Echec technique de l'agent ({type(exc).__name__})",
                    en=f"Agent technical failure ({type(exc).__name__})",
                ),
            )

        out.agent_id = self.id
        out.started_at = started
        out.finished_at = datetime.now(timezone.utc)
        out.duration_ms = int((time.perf_counter() - t0) * 1000)
        if out.status is AgentStatus.IDLE:
            out.status = AgentStatus.DONE
        return out

    @abstractmethod
    async def run(self, ctx: RunContext) -> AgentOutput:
        """Logique propre a l'agent. En V1: derivee des features simulees."""
        raise NotImplementedError
