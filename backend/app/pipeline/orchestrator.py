"""
Orchestration du comite.

Pipeline : Donnees -> [Technique | Macro | Futures | Evenements] en parallele
-> Red Team -> un seul tour de reponse aux objections -> Risk Manager -> CIO.

Choix d'architecture arbitres avec Hermes :

  - asyncio suffit. Temporal brille pour du multi-machine et du long-running
    distribue ; sur un VPS mono-hote avec un pipeline sous la minute, c'est du
    poids mort.

  - FAIL-CLOSED. Si un analyste tombe ou depasse son temps, on ne laisse pas un
    vote partiel passer : la sortie est NO TRADE. En trading, l'ambiguite n'est
    pas un signal faible, c'est une absence de signal.

  - UN SEUL tour de rebuttal. Au-dela, la latence et le cout explosent sans
    gain mesurable.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.agents import registry
from app.agents.base import RunContext
from app.features import engine
from app.mock import fixtures
from app.schemas import (
    AgentOutput,
    AgentStatus,
    Direction,
    EventRisk,
    Localized,
    Run,
    RiskVerdict,
    RunStage,
    RunTrigger,
    TriggerCandidate,
    TriggerPriority,
    Timeframe,
)

ANALYST_TIMEOUT_S = 25.0
MAX_REBUTTAL_ROUNDS = 1


def build_market_snapshot(seed: int = fixtures.SEED) -> dict:
    """
    Instantane complet, fige a T.

    Tout ce que les agents liront pendant le run vient de ce dictionnaire et de
    nulle part ailleurs. C'est la condition du point-in-time correctness : si un
    agent pouvait relire la source en direct, deux agents du meme run
    travailleraient sur des donnees differentes.
    """
    market = fixtures.build_market(seed=seed)
    fv = engine.build_feature_vector(market)
    calendar = fixtures.calendar()
    df5 = market["5m"]

    return {
        "frames": market,
        "features": fv,
        "reads": engine.analyse_timeframes(market),
        "levels": engine.ind.key_levels(market["1H"], fv.spot),
        "sources": fixtures.data_sources(),
        "macro": fixtures.macro_snapshot(seed=seed),
        "futures": fixtures.futures_snapshot(market, seed=seed),
        "calendar": calendar,
        "change_pct": float(
            (df5["close"].iloc[-1] - df5["close"].iloc[-12]) / df5["close"].iloc[-12] * 100
        ),
        "triggers": engine.detect_triggers(market, fv, calendar),
    }


def manual_trigger() -> TriggerCandidate:
    now = datetime.now(timezone.utc)
    return TriggerCandidate(
        kind="manual",
        priority=TriggerPriority.HIGH,
        dedup_key=f"manual:{now.isoformat()}",
        timeframe=Timeframe.M5,
        detected_at=now,
        reason=Localized(
            fr="Analyse demandée manuellement par l'utilisateur.",
            en="Analysis manually requested by the user.",
        ),
    )


class Orchestrator:
    """Execute un run complet et publié l'avancement etape par etape."""

    def __init__(self, on_event=None) -> None:
        self._on_event = on_event

    async def _emit(self, run: Run, stage: RunStage) -> None:
        run.stage = stage
        if self._on_event:
            await self._on_event(run)

    # ------------------------------------------------------------------
    async def run(
        self,
        trigger: TriggerCandidate | None = None,
        seed: int = fixtures.SEED,
    ) -> Run:
        trigger = trigger or manual_trigger()
        snapshot = build_market_snapshot(seed=seed)
        fv = snapshot["features"]

        run = Run(
            run_id=uuid.uuid4().hex[:12],
            started_at=datetime.now(timezone.utc),
            trigger=(RunTrigger.MANUAL if trigger.kind == "manual"
                     else RunTrigger.SETUP_CANDIDATE),
            stage=RunStage.DATA,
            spot_at_decision=fv.spot,
            input_snapshot={
                "feature_schema_version": fv.schema_version,
                "as_of": fv.as_of.isoformat(),
                "contract": fv.contract.symbol,
                "series_type": fv.contract.series_type,
                "trigger": trigger.model_dump(mode="json"),
                "sources": [s.model_dump(mode="json") for s in snapshot["sources"]],
            },
        )

        ctx = RunContext(
            run_id=run.run_id,
            trigger=trigger,
            features=fv,
            market=snapshot,
        )

        # -- Etape 1 : donnees -------------------------------------------
        await self._emit(run, RunStage.DATA)
        data_out = await registry.get("data_market_state").execute(ctx)
        run.outputs["data_market_state"] = data_out

        if ctx.halted:
            # La fondation a coupe : personne d'autre ne parle.
            for agent in registry.AGENTS[1:]:
                run.outputs[agent.id] = AgentOutput(
                    agent_id=agent.id,
                    status=AgentStatus.BLOCKED,
                    headline=ctx.halt_reason,
                )
            run.decision = Direction.NO_TRADE
            run.halted = True
            run.finished_at = datetime.now(timezone.utc)
            await self._emit(run, RunStage.HALTED)
            return run

        ctx.outputs = run.outputs

        # -- Etape 2 : fan-out des analystes -----------------------------
        await self._emit(run, RunStage.ANALYSIS)
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(registry.get(aid).execute(ctx) for aid in registry.ANALYST_IDS),
                    return_exceptions=True,
                ),
                timeout=ANALYST_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            results = [None] * len(registry.ANALYST_IDS)

        failed: list[str] = []
        for aid, res in zip(registry.ANALYST_IDS, results):
            if isinstance(res, AgentOutput) and res.status is AgentStatus.DONE:
                run.outputs[aid] = res
            else:
                failed.append(aid)
                run.outputs[aid] = AgentOutput(
                    agent_id=aid,
                    status=AgentStatus.FAILED,
                    headline=Localized(
                        fr="Analyste indisponible : son vote est écarté.",
                        en="Analyst unavailable: its vote is discarded.",
                    ),
                )
        ctx.outputs = run.outputs

        if failed:
            # Fail-closed : un analyste mort ne laisse pas passer un vote partiel.
            return await self._fail_closed(run, failed)

        # -- Etape 3 : Red Team ------------------------------------------
        await self._emit(run, RunStage.RED_TEAM)
        run.outputs["red_team"] = await registry.get("red_team").execute(ctx)
        ctx.outputs = run.outputs

        # -- Etape 4 : un tour de reponse aux objections -----------------
        await self._emit(run, RunStage.REBUTTAL)
        self._rebuttal(ctx, run)

        # -- Etape 5 : risque --------------------------------------------
        await self._emit(run, RunStage.RISK)
        run.outputs["risk_manager"] = await registry.get("risk_manager").execute(ctx)
        ctx.outputs = run.outputs
        # Coercition explicite : le payload est du JSON, pas des enums.
        run.risk_verdict = RiskVerdict(run.outputs["risk_manager"].payload["verdict"])

        # -- Etape 6 : decision ------------------------------------------
        await self._emit(run, RunStage.DECISION)
        cio_out = await registry.get("cio").execute(ctx)
        run.outputs["cio"] = cio_out

        run.decision = cio_out.direction
        run.conviction = cio_out.conviction
        run.event_risk = EventRisk(run.outputs["event"].payload["level"])
        ticket = cio_out.payload.get("ticket")
        if ticket:
            from app.schemas import TradeTicket
            run.ticket = TradeTicket.model_validate(ticket)

        run.finished_at = datetime.now(timezone.utc)
        await self._emit(run, RunStage.COMPLETE)
        return run

    # ------------------------------------------------------------------
    async def _fail_closed(self, run: Run, failed: list[str]) -> Run:
        reason = Localized(
            fr=f"{len(failed)} analyste(s) indisponible(s) ({', '.join(failed)}). "
               "Le système refuse de décider sur une analyse partielle.",
            en=f"{len(failed)} analyst(s) unavailable ({', '.join(failed)}). "
               "The system refuses to decide on a partial analysis.",
        )
        for aid in ("red_team", "risk_manager", "cio"):
            run.outputs[aid] = AgentOutput(
                agent_id=aid, status=AgentStatus.SKIPPED, headline=reason,
            )
        run.decision = Direction.NO_TRADE
        run.conviction = 0
        run.halted = True
        run.finished_at = datetime.now(timezone.utc)
        await self._emit(run, RunStage.HALTED)
        return run

    # ------------------------------------------------------------------
    def _rebuttal(self, ctx: RunContext, run: Run) -> None:
        """
        Un seul tour. Chaque analyste vise par une objection y repond, et
        l'objection est marquee comme tenant toujours ou non.

        Une objection de severite 4 ou plus ne peut pas etre levee par une
        simple reponse : elle reste au dossier et penalise la conviction finale.
        """
        red = run.outputs.get("red_team")
        if not red or not red.payload.get("hypotheses"):
            return

        hypotheses = red.payload["hypotheses"]
        for h in hypotheses:
            targets = h.get("targets") or []
            answered = False
            for target in targets:
                out = run.outputs.get(target)
                if not out or out.status is not AgentStatus.DONE:
                    continue
                h["rebuttal"] = {
                    "fr": f"{_agent_name(target, 'fr')} maintient sa lecture mais "
                          f"reconnait le point : la conviction est revue a la baisse.",
                    "en": f"{_agent_name(target, 'en')} maintains its reading but "
                          f"acknowledges the point: conviction is revised down.",
                }
                answered = True
                break

            # Les objections graves survivent a la reponse.
            h["rebuttal_holds"] = h["severity"] >= 4 or not answered

        red.payload["hypotheses"] = hypotheses
        red.payload["unresolved_count"] = sum(
            1 for h in hypotheses if h.get("rebuttal_holds")
        )


def _agent_name(agent_id: str, lang: str) -> str:
    card = registry.get(agent_id).card()
    return getattr(card.name, lang)
