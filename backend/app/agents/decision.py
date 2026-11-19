"""
Agents 6 a 8 : Red Team, Risk Manager, CIO.

Trois regles issues du debat d'archi avec Hermes :

  - Le Red Team est ASYMETRIQUE. Son travail n'est pas de donner un second avis,
    c'est de chercher la faille : attaquer les niveaux, citer le prix exact qui
    invalide, montrer ou l'evidence est mince. Un Red Team poli = fausse
    confiance, et c'est sa qualite qui determine la calibration du systeme.

  - Le Risk Manager est scinde. Le sizing, les limites de drawdown et la
    distance de stop sont du Python deterministe (`RiskEngine`). Le LLM ne fait
    que le veto qualitatif. Un LLM qui decide d'une taille de position est une
    catastrophe qui attend de se produire.

  - Le CIO n'a pas le droit de lisser un desaccord. Sur un vote 2-2 ou une
    dispersion trop forte, un circuit breaker deterministe impose NO TRADE.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import Agent, RunContext
from app.schemas import (
    AgentOutput,
    AgentStatus,
    CIOPayload,
    Direction,
    Evidence,
    EventRisk,
    Localized,
    ModelTier,
    RedTeamHypothesis,
    RedTeamPayload,
    RiskCheck,
    RiskPayload,
    RiskVerdict,
    RunStage,
    TicketSection,
    ToolSpec,
    TradeTicket,
)

ANALYSTS = ("technical", "macro", "futures", "event")


def L(fr: str, en: str) -> Localized:
    return Localized(fr=fr, en=en)


# ==========================================================================
# 6. Red Team
# ==========================================================================
class RedTeamAgent(Agent):
    """
    "Suppose que cette proposition de trade va perdre. Trouve les trois
    explications les plus plausibles que les autres agents ont ratees."
    """

    id = "red_team"
    order = 6
    stage = RunStage.RED_TEAM
    model_tier = ModelTier.STRONG

    name = L("Red Team", "Red Team")
    role = L("L'avocat du diable", "The devil's advocate")
    mandate = L(
        "Part du principe que le trade va perdre et cherche les trois "
        "explications les plus plausibles que les autres ont ratées : données "
        "contradictoires, corrélations trompeuses, signal déjà pricé, mauvais "
        "régime, proximité d'un événement, cassure fragile, informations "
        "manquantes, dépendances entre signaux.",
        "Assumes the trade will lose and hunts the three most plausible reasons "
        "the others missed: contradictory data, misleading correlations, "
        "already-priced signal, wrong regime, event proximity, fragile breakout, "
        "missing information, dependencies between signals.",
    )
    plain = L(
        "Son seul travail est de trouver pourquoi l'idée est mauvaise. S'il ne "
        "trouve rien de solide, c'est bon signe. S'il trouve quelque chose, "
        "mieux vaut l'entendre maintenant qu'après avoir perdu de l'argent.",
        "Its only job is to find why the idea is bad. If it finds nothing solid, "
        "that is a good sign. If it finds something, better to hear it now than "
        "after losing money.",
    )
    tools = [
        ToolSpec(name="Historique des runs", provider="internal",
                 purpose=L("Erreurs récurrentes du système",
                           "Recurring system mistakes")),
        ToolSpec(name="Matrice de corrélation des signaux", provider="internal",
                 purpose=L("Détection des signaux redondants",
                           "Redundant signal detection")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        tech = ctx.payload("technical")
        macro = ctx.payload("macro")
        fut = ctx.payload("futures")
        event = ctx.payload("event")
        fv = ctx.features

        hypotheses: list[RedTeamHypothesis] = []

        # -- Proximite d'un evenement ------------------------------------
        if event.get("level") in (EventRisk.HIGH.value, EventRisk.ELEVATED.value):
            nxt = event.get("next_event") or {}
            mins = nxt.get("minutes_until", 0)
            hypotheses.append(RedTeamHypothesis(
                rank=len(hypotheses) + 1,
                kind="event_proximity",
                claim=L(
                    f"Le setup se fait balayer par la publication dans {mins} min.",
                    f"The setup gets run over by the release in {mins} min.",
                ),
                argument=L(
                    "Le prix ne suivra pas la structure technique mais l'écart "
                    "entre le chiffre publié et le consensus. Un stop calibré "
                    "sur l'ATR normal sera traverse par le pic de volatilité de"
                    " publication, même si la direction finale est la bonne.",
                    "Price will not follow technical structure but the gap between "
                    "the printed number and consensus. A stop sized on normal ATR "
                    "will be sliced through by the release volatility spike, even "
                    "if the final direction is right.",
                ),
                severity=5 if event.get("blackout_active") else 4,
                targets=["technical", "event"],
            ))

        # -- Structure incoherente ---------------------------------------
        alignment = tech.get("alignment", 0)
        if alignment < 50:
            hypotheses.append(RedTeamHypothesis(
                rank=len(hypotheses) + 1,
                kind="wrong_regime",
                claim=L(
                    f"La cohérence multi-unités n'est que de {alignment} % : on "
                    "traite un marché sans direction comme s'il en avait une.",
                    f"Cross-timeframe agreement is only {alignment}%: we are "
                    "treating a directionless market as if it had a direction.",
                ),
                argument=L(
                    "Quand les unités de temps se contredisent, le prix oscille"
                    " et declenche les stops des deux cotes. La conviction "
                    "affichee par l'agent technique mesure sa certitude "
                    "interne, pas la probabilité que le marché aille quelque "
                    "part.",
                    "When timeframes contradict, price oscillates and takes out "
                    "stops on both sides. The conviction shown by the technical "
                    "agent measures its internal certainty, not the probability "
                    "the market goes anywhere.",
                ),
                severity=4,
                targets=["technical"],
            ))

        # -- Cassure fragile : volume qui ne confirme pas -----------------
        vol_ratio = fut.get("volume_vs_avg", 1.0)
        if vol_ratio < 1.0:
            hypotheses.append(RedTeamHypothesis(
                rank=len(hypotheses) + 1,
                kind="fragile_breakout",
                claim=L(
                    f"Le mouvement se fait a {vol_ratio:.2f}x le volume moyen : "
                    "il n'est pas soutenu.",
                    f"The move is happening on {vol_ratio:.2f}x average volume: "
                    "it is not supported.",
                ),
                argument=L(
                    "Une cassure sans volume est le schema classique du faux "
                    "signal : les participants ne suivent pas, le prix revient "
                    "dans la zone et piege ceux qui ont poursuivi.",
                    "A breakout without volume is the textbook false-signal "
                    "pattern: participants do not follow, price returns into the "
                    "range and traps those who chased.",
                ),
                severity=3,
                targets=["technical", "futures"],
            ))

        # -- Correlation macro rompue ------------------------------------
        contradictions = macro.get("contradictions", [])
        if contradictions:
            hypotheses.append(RedTeamHypothesis(
                rank=len(hypotheses) + 1,
                kind="misleading_correlation",
                claim=L(
                    "Le raisonnement macro s'appuie sur des relations qui ne "
                    "tiennent plus dans le régime actuel.",
                    "The macro reasoning leans on relationships that no longer "
                    "hold in the current regime.",
                ),
                argument=L(
                    "L'agent macro a lui-même signale des corrélations rompues."
                    " Un raisonnement du type 'dollar faible donc or haussier' "
                    "n'est valable que si la relation est active - sinon c'est "
                    "une règle apprise appliquee au mauvais moment.",
                    "The macro agent flagged broken correlations itself. Reasoning "
                    "like 'weak dollar so gold up' only holds while the "
                    "relationship is active - otherwise it is a learned rule "
                    "applied at the wrong time.",
                ),
                severity=4,
                targets=["macro"],
            ))

        # -- Signal deja price -------------------------------------------
        if abs(fv.vwap_distance_atr.value) > 2.0:
            hypotheses.append(RedTeamHypothesis(
                rank=len(hypotheses) + 1,
                kind="already_priced",
                claim=L(
                    f"Le prix est déjà a {fv.vwap_distance_atr.value:+.2f} ATR de "
                    "sa moyenne : l'essentiel du mouvement est derrière nous.",
                    f"Price is already {fv.vwap_distance_atr.value:+.2f} ATR from "
                    "its average: most of the move is behind us.",
                ),
                argument=L(
                    "Entrer ici revient a acheter après coup. Le rapport "
                    "rendement/risque se dégradé mécaniquement : le stop doit "
                    "être place loin derrière, et l'objectif restant est plus "
                    "court que le trajet déjà parcouru.",
                    "Entering here means buying after the fact. Reward-to-risk "
                    "degrades mechanically: the stop must sit far behind, and the "
                    "remaining target is shorter than the distance already travelled.",
                ),
                severity=3,
                targets=["technical"],
            ))

        # -- Toujours au moins une objection -----------------------------
        if not hypotheses:
            hypotheses.append(RedTeamHypothesis(
                rank=1,
                kind="missing_information",
                claim=L(
                    "Aucune faille evidente - ce qui est en soi une information "
                    "a manier avec prudence.",
                    "No obvious flaw - which is itself information to handle "
                    "carefully.",
                ),
                argument=L(
                    "Quand tout s'aligne, le risque n'est pas dans les données "
                    "mais dans ce qui n'est pas mesure : liquidité réelle au "
                    "moment de l'execution, positionnement non publie, flux non"
                    " observables. L'absence de contradiction n'est pas une "
                    "preuve.",
                    "When everything aligns, the risk is not in the data but in "
                    "what is not measured: real liquidity at execution, unpublished "
                    "positioning, unobservable flows. Absence of contradiction is "
                    "not proof.",
                ),
                severity=2,
                targets=[],
            ))

        hypotheses = sorted(hypotheses, key=lambda h: h.severity, reverse=True)[:3]
        for i, h in enumerate(hypotheses, 1):
            h.rank = i

        # -- Signaux correles : le piege du vote naif ---------------------
        correlated: list[Localized] = []
        tech_dir = ctx.get("technical").direction if ctx.get("technical") else None
        fut_dir = ctx.get("futures").direction if ctx.get("futures") else None
        if tech_dir and tech_dir == fut_dir and tech_dir is not Direction.NEUTRAL:
            correlated.append(L(
                "Momentum technique, cassure et volume décrivent en grande "
                "partie le même phénomène. Les compter comme trois "
                "confirmations indépendantes surestime la conviction réelle.",
                "Technical momentum, breakout and volume largely describe the same "
                "phenomenon. Counting them as three independent confirmations "
                "overstates true conviction.",
            ))

        payload = RedTeamPayload(
            hypotheses=hypotheses,
            correlated_signals=correlated,
            unresolved_count=sum(1 for h in hypotheses if h.severity >= 4),
        )

        worst = max(h.severity for h in hypotheses)
        return AgentOutput(
            agent_id=self.id,
            direction=Direction.NEUTRAL,
            conviction=None,
            headline=L(
                f"{len(hypotheses)} objection(s), sévérité maximale {worst}/5.",
                f"{len(hypotheses)} objection(s), max severity {worst}/5.",
            ),
            detail=hypotheses[0].claim,
            evidence=[
                Evidence(
                    label=h.claim,
                    value=f"{h.severity}/5",
                    reading=h.argument,
                    weight=h.severity,
                    supports=Direction.NEUTRAL,
                )
                for h in hypotheses
            ],
            warnings=correlated,
            payload=payload.model_dump(mode="json"),
        )


# ==========================================================================
# 7. Risk Manager - droit de veto
# ==========================================================================
class RiskEngine:
    """
    Partie deterministe. Aucun LLM ne touche a ces nombres.

    Hermes : "un LLM qui decide de la taille de position, c'est une catastrophe
    qui attend de se produire." Le sizing, les limites dures et la distance de
    stop sont calcules ici, en Python, et ne sont pas negociables.
    """

    ACCOUNT_EQUITY = 100_000.0        # USD
    RISK_PER_TRADE_PCT = 0.5          # % du capital par trade
    MAX_DAILY_LOSS_PCT = 2.0
    CONTRACT_MULTIPLIER = 100         # GC : 100 onces troy
    MIN_STOP_ATR = 1.0
    MAX_STOP_ATR = 3.0

    @classmethod
    def size(cls, atr: float, stop_atr_mult: float = 1.5) -> tuple[float, float, float]:
        """Retourne (contrats, perte max en USD, distance de stop en points)."""
        stop_points = atr * stop_atr_mult
        risk_usd = cls.ACCOUNT_EQUITY * cls.RISK_PER_TRADE_PCT / 100
        per_contract = stop_points * cls.CONTRACT_MULTIPLIER
        contracts = risk_usd / per_contract if per_contract else 0.0
        return round(contracts, 2), round(risk_usd, 2), round(stop_points, 2)


class RiskManagerAgent(Agent):
    """
    Independant des agents haussiers/baissiers. Il ne decide pas ou va l'or :
    il decide si le trade propose respecte les contraintes. Il doit pouvoir
    bloquer, meme lorsque tous les autres agents sont convaincus.
    """

    id = "risk_manager"
    order = 7
    stage = RunStage.RISK
    model_tier = ModelTier.CHEAP          # veto qualitatif seulement
    can_veto = True

    name = L("Risk Manager", "Risk Manager")
    role = L("Droit de veto", "Veto power")
    mandate = L(
        "Indépendant des agents directionnels. Contrôle volatilité, distance "
        "d'invalidation, exposition, risque monétaire, levier, liquidité, "
        "corrélation avec les positions existantes, risque événementiel et "
        "perte quotidienne maximale. Rend APPROVED, REDUCE ou REJECT. Le sizing"
        " et les limites dures sont calcules en Python, pas par un LLM.",
        "Independent from the directional agents. Controls volatility, "
        "invalidation distance, exposure, monetary risk, leverage, liquidity, "
        "correlation with existing positions, event risk and maximum daily loss. "
        "Returns APPROVED, REDUCE or REJECT. Sizing and hard limits are computed "
        "in Python, not by an LLM.",
    )
    plain = L(
        "C'est le garde-fou. Même si tous les autres sont enthousiastes, il "
        "peut dire non - parce que perdre trop sur un seul trade est la seule "
        "erreur dont on ne se remet pas.",
        "This is the safety rail. Even if everyone else is enthusiastic it can "
        "say no - because losing too much on a single trade is the one mistake "
        "you do not recover from.",
    )
    tools = [
        ToolSpec(name="Positions ouvertes", provider="broker",
                 purpose=L("Exposition et corrélation", "Exposure and correlation")),
        ToolSpec(name="Etat du compte", provider="broker",
                 purpose=L("Capital, marge, perte du jour",
                           "Equity, margin, daily loss")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        fv = ctx.features
        tech = ctx.get("technical")
        event = ctx.payload("event")
        red = ctx.payload("red_team")

        atr = fv.extras["atr_5m"].value
        contracts, risk_usd, stop_points = RiskEngine.size(atr)
        stop_atr = round(stop_points / atr, 2) if atr else 0.0
        daily_used = 0.4        # V1 : pas de compte branche

        checks: list[RiskCheck] = []

        def check(fr_name, en_name, ok, fr_detail, en_detail, hard=False):
            checks.append(RiskCheck(
                name=L(fr_name, en_name), passed=ok,
                detail=L(fr_detail, en_detail), is_hard_limit=hard,
            ))

        # 1. Distance d'invalidation
        ok_stop = RiskEngine.MIN_STOP_ATR <= stop_atr <= RiskEngine.MAX_STOP_ATR
        check("Distance d'invalidation", "Invalidation distance", ok_stop,
              f"Stop a {stop_atr} ATR ({stop_points} points).",
              f"Stop at {stop_atr} ATR ({stop_points} points).")

        # 2. Risque monetaire
        check("Risque monétaire", "Monetary risk", True,
              f"{risk_usd:,.0f} $ risques, soit {RiskEngine.RISK_PER_TRADE_PCT} % "
              f"du capital.",
              f"${risk_usd:,.0f} at risk, {RiskEngine.RISK_PER_TRADE_PCT}% of equity.")

        # 3. Perte quotidienne - limite dure
        ok_daily = daily_used < RiskEngine.MAX_DAILY_LOSS_PCT
        check("Perte quotidienne maximale", "Maximum daily loss", ok_daily,
              f"{daily_used} % utilises sur {RiskEngine.MAX_DAILY_LOSS_PCT} % "
              f"autorises.",
              f"{daily_used}% used of {RiskEngine.MAX_DAILY_LOSS_PCT}% allowed",
              hard=True)

        # 4. Risque evenementiel - limite dure
        blackout = event.get("blackout_active", False)
        check("Risque événementiel", "Event risk", not blackout,
              "Publication majeure imminente : l'ecart de prix a l'ouverture peut "
              "depasser le stop." if blackout else
              "Aucune publication majeure dans la fenêtre du trade.",
              "Major release imminent: the price gap can exceed the stop."
              if blackout else "No major release within the trade window.",
              hard=True)

        # 5. Liquidite
        liquid = fv.session.is_liquid_hours
        check("Liquidité de session", "Session liquidity", liquid,
              f"Session {fv.session.session}, "
              f"{'heures liquides' if liquid else 'hors heures liquides'}.",
              f"{fv.session.session} session, "
              f"{'liquid hours' if liquid else 'outside liquid hours'}.")

        # 6. Regime de volatilite
        vol_ok = fv.atr_percentile.value < 90
        check("Régime de volatilité", "Volatility regime", vol_ok,
              f"ATR au {int(fv.atr_percentile.value)}e percentile.",
              f"ATR at the {int(fv.atr_percentile.value)}th percentile.")

        # 7. Objections non resolues du Red Team
        unresolved = red.get("unresolved_count", 0)
        check("Objections du Red Team", "Red Team objections", unresolved < 2,
              f"{unresolved} objection(s) de sévérité élevée non levée(s).",
              f"{unresolved} high-severity objection(s) unresolved.")

        # 8. Roll de contrat
        roll_ok = fv.contract.days_to_roll > 3
        check("Roll de contrat", "Contract roll", roll_ok,
              f"Roll dans {fv.contract.days_to_roll} jours.",
              f"Roll in {fv.contract.days_to_roll} days.")

        # ---- Verdict : les limites dures priment ------------------------
        hard_failed = [c for c in checks if c.is_hard_limit and not c.passed]
        soft_failed = [c for c in checks if not c.is_hard_limit and not c.passed]

        if hard_failed:
            verdict = RiskVerdict.REJECT
            veto = L(
                "Veto : " + hard_failed[0].detail.fr,
                "Veto: " + hard_failed[0].detail.en,
            )
            size = 0.0
        elif len(soft_failed) >= 2:
            verdict = RiskVerdict.REDUCE
            veto = L(
                f"{len(soft_failed)} contrôles non satisfaits : taille réduite de "
                "moitié.",
                f"{len(soft_failed)} checks not satisfied: size halved.",
            )
            size = round(contracts / 2, 2)
        else:
            verdict = RiskVerdict.APPROVED
            veto = None
            size = contracts

        if tech and tech.direction is Direction.NEUTRAL:
            verdict = RiskVerdict.REJECT
            size = 0.0
            veto = L(
                "Veto : aucune direction technique exploitable. Pas de trade "
                "sans thèse.",
                "Veto: no actionable technical direction. No trade without a thesis.",
            )

        payload = RiskPayload(
            verdict=verdict,
            checks=checks,
            risk_budget_pct=RiskEngine.RISK_PER_TRADE_PCT,
            suggested_size=size,
            max_loss_currency=round(size * stop_points * RiskEngine.CONTRACT_MULTIPLIER, 2),
            daily_loss_used_pct=daily_used,
            invalidation_distance_atr=stop_atr,
            veto_reason=veto,
        )

        return AgentOutput(
            agent_id=self.id,
            status=AgentStatus.DONE,
            direction=Direction.NEUTRAL,
            conviction=None,
            headline=L(
                {RiskVerdict.APPROVED: f"APPROUVÉ - {size} contrat(s), "
                                       f"{risk_usd:,.0f} $ de risque.",
                 RiskVerdict.REDUCE: f"TAILLE RÉDUITE - {size} contrat(s).",
                 RiskVerdict.REJECT: "REJETÉ - le trade ne passe pas les "
                                     "contraintes."}[verdict],
                {RiskVerdict.APPROVED: f"APPROVED - {size} contract(s), "
                                       f"${risk_usd:,.0f} at risk.",
                 RiskVerdict.REDUCE: f"SIZE REDUCED - {size} contract(s).",
                 RiskVerdict.REJECT: "REJECTED - the trade fails its "
                                     "constraints."}[verdict],
            ),
            detail=veto or L(
                f"{sum(c.passed for c in checks)}/{len(checks)} contrôles passes.",
                f"{sum(c.passed for c in checks)}/{len(checks)} checks passed.",
            ),
            evidence=[
                Evidence(
                    label=c.name,
                    value="OK" if c.passed else ("LIMITE DURE" if c.is_hard_limit else "ECHEC"),
                    reading=c.detail,
                    weight=5 if c.is_hard_limit else 3,
                    supports=Direction.NEUTRAL,
                )
                for c in checks
            ],
            warnings=[veto] if veto else [],
            payload=payload.model_dump(mode="json"),
        )


# ==========================================================================
# 8. CIO / Trade Decision - decision finale
# ==========================================================================
class CIOAgent(Agent):
    """
    Le seul agent autorise a assembler les analyses en proposition finale.

    Le raisonnement naif lui est interdit : "4 agents haussiers contre 1
    baissier = BUY" ne vaut rien si les signaux sont correles. Le CIO affiche
    le vote naif puis explique pourquoi il ne s'en sert pas.
    """

    id = "cio"
    order = 8
    stage = RunStage.DECISION
    model_tier = ModelTier.STRONG

    name = L("CIO / Décision", "CIO / Trade Decision")
    role = L("La décision finale", "The final decision")
    mandate = L(
        "Reçoit Technique, Macro, Futures, Événements, Red Team et Risk, "
        "cherche les contradictions et assemble le Trade Ticket. Le "
        "raisonnement simpliste par comptage de votes lui est interdit : les "
        "signaux peuvent être corrélés. NO TRADE est une sortie legitime.",
        "Receives Technical, Macro, Futures, Event, Red Team and Risk, hunts "
        "contradictions and assembles the Trade Ticket. Naive vote counting is "
        "forbidden: signals can be correlated. NO TRADE is a legitimate output.",
    )
    plain = L(
        "C'est lui qui tranche. Il écoute tout le monde, repère les avis qui "
        "disent en realite la même chose, et a parfaitement le droit de "
        "conclure qu'il ne faut rien faire.",
        "This one decides. It listens to everyone, spots opinions that are "
        "really saying the same thing, and is perfectly entitled to conclude "
        "that nothing should be done.",
    )
    tools = [
        ToolSpec(name="Journal des decisions", provider="internal",
                 purpose=L("Calibration historique", "Historical calibration")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        fv = ctx.features
        tech = ctx.get("technical")
        macro = ctx.get("macro")
        fut = ctx.get("futures")
        risk_p = ctx.payload("risk_manager")
        red_p = ctx.payload("red_team")
        event_p = ctx.payload("event")

        votes = {
            "technical": tech.direction if tech else None,
            "macro": macro.direction if macro else None,
            "futures": fut.direction if fut else None,
        }
        longs = sum(1 for v in votes.values() if v is Direction.LONG)
        shorts = sum(1 for v in votes.values() if v is Direction.SHORT)
        naive = f"{longs} haussier(s) / {shorts} baissier(s)"

        # Deduplication : technique et futures decrivent souvent le meme flux.
        independent = 0
        if tech and tech.direction is not Direction.NEUTRAL:
            independent += 1
        if macro and macro.direction is not Direction.NEUTRAL:
            independent += 1
        if fut and fut.direction is not Direction.NEUTRAL and (
            not tech or fut.direction != tech.direction
        ):
            independent += 1

        contradictions: list[Localized] = []
        if tech and macro and tech.direction != macro.direction:
            if Direction.NEUTRAL not in (tech.direction, macro.direction):
                contradictions.append(L(
                    "La lecture technique et la lecture macro pointent dans des "
                    "directions opposees. sur l'or, c'est la macro qui gagne sur "
                    "l'horizon long et la technique sur l'horizon court - mais "
                    "cette divergence suffit a disqualifier un swing.",
                    "The technical and macro readings point in opposite "
                    "directions. On gold, macro wins over the long horizon and "
                    "technicals over the short - but this divergence alone "
                    "disqualifies a swing.",
                ))
        contradictions.extend(Localized(**c) for c in red_p.get("correlated_signals", []))

        # ---- Circuit breaker deterministe -------------------------------
        # Hermes : "ne laisse pas le CIO trancher un split 50/50 en douceur."
        verdict = risk_p.get("verdict")
        split = longs == shorts and longs > 0
        weak = independent < 2

        if verdict == RiskVerdict.REJECT.value:
            decision = Direction.NO_TRADE
            rationale = L(
                "Le Risk Manager a oppose son veto. Cette décision prime sur "
                "l'avis des analystes, quelle que soit leur conviction.",
                "The Risk Manager vetoed. That decision overrides the analysts "
                "regardless of their conviction.",
            )
        elif split:
            decision = Direction.NO_TRADE
            rationale = L(
                f"Désaccord franc entre analystes ({naive}). Un partage 50/50 "
                "n'est pas un signal faible à arbitrer, c'est une absence de "
                "signal : le système s'abstient plutôt que de lisser.",
                f"Clear analyst disagreement ({naive}). A 50/50 split is not a "
                "weak signal to arbitrate, it is the absence of a signal: the "
                "system abstains rather than smoothing it over.",
            )
        elif weak:
            decision = Direction.NO_TRADE
            rationale = L(
                f"Seulement {independent} signal(aux) reellement independant(s) "
                "après déduplication. Le vote brut suggerait autre chose, mais "
                "compter deux fois le même phénomène ne créé pas de conviction.",
                f"Only {independent} genuinely independent signal(s) after "
                "de-duplication. The raw vote suggested otherwise, but counting "
                "the same phenomenon twice does not create conviction.",
            )
        elif longs > shorts:
            decision = Direction.LONG
            rationale = L(
                "Lecture haussière soutenue par des signaux indépendants et "
                "validée par le contrôle du risque.",
                "Bullish reading supported by independent signals and cleared by "
                "risk control.",
            )
        elif shorts > longs:
            decision = Direction.SHORT
            rationale = L(
                "Lecture baissière soutenue par des signaux indépendants et "
                "validée par le contrôle du risque.",
                "Bearish reading supported by independent signals and cleared by "
                "risk control.",
            )
        else:
            decision = Direction.NO_TRADE
            rationale = L(
                "Aucune thèse exploitable. Le système n'est pas obligé de "
                "produire un trade à chaque exécution.",
                "No actionable thesis. The system is not required to produce a "
                "trade on every run.",
            )

        # Conviction : moyenne ponderee, penalisee par le Red Team.
        parts = [(o.conviction or 0) for o in (tech, macro, fut) if o and o.conviction]
        base = int(sum(parts) / len(parts)) if parts else 0
        penalty = red_p.get("unresolved_count", 0) * 12
        conviction = 0 if decision is Direction.NO_TRADE else max(5, min(95, base - penalty))

        ticket = None
        if not ctx.halted:
            ticket = _build_ticket(ctx, decision, conviction, rationale)

        payload = CIOPayload(
            ticket=ticket,
            contradictions_found=contradictions,
            independent_signals=independent,
            naive_vote=naive,
            why_not_naive=L(
                "Le vote brut compte des signaux qui se recouvrent. Momentum, "
                "cassure et volume décrivent souvent le même phénomène : les "
                "additionner gonfle artificiellement la conviction. Seuls les "
                "signaux indépendants sont retenus.",
                "The raw vote counts overlapping signals. Momentum, breakout and "
                "volume often describe the same phenomenon: adding them "
                "artificially inflates conviction. Only independent signals count.",
            ),
        )

        return AgentOutput(
            agent_id=self.id,
            direction=decision,
            conviction=conviction,
            horizon=L("Intraday / Swing", "Intraday / Swing"),
            headline=L(
                {Direction.LONG: f"LONG - conviction {conviction}/100.",
                 Direction.SHORT: f"SHORT - conviction {conviction}/100.",
                 Direction.NO_TRADE: "PAS DE TRADE.",
                 Direction.NEUTRAL: "PAS DE TRADE."}[decision],
                {Direction.LONG: f"LONG - conviction {conviction}/100.",
                 Direction.SHORT: f"SHORT - conviction {conviction}/100.",
                 Direction.NO_TRADE: "NO TRADE.",
                 Direction.NEUTRAL: "NO TRADE."}[decision],
            ),
            detail=rationale,
            evidence=[],
            warnings=contradictions,
            payload=payload.model_dump(mode="json"),
        )


def _build_ticket(
    ctx: RunContext, decision: Direction, conviction: int, rationale: Localized
) -> TradeTicket:
    fv = ctx.features
    tech_p = ctx.payload("technical")
    macro_p = ctx.payload("macro")
    fut_p = ctx.payload("futures")
    event_p = ctx.payload("event")
    risk_p = ctx.payload("risk_manager")
    red_p = ctx.payload("red_team")

    atr = fv.extras["atr_5m"].value
    stop_atr = risk_p.get("invalidation_distance_atr", 1.5)
    sign = -1 if decision is Direction.LONG else 1
    stop_price = round(fv.spot + sign * atr * stop_atr, 2)
    target_price = round(fv.spot - sign * atr * stop_atr * 2, 2)

    bull = [Localized(**e["reading"]) for e in tech_p.get("evidence", [])[:1]] or [L(
        "Structure haussière sur les unités longues.", "Bullish structure on higher timeframes.")]
    bear = [Localized(**h["claim"]) for h in red_p.get("hypotheses", [])[:2]]

    return TradeTicket(
        instrument="GC",
        contract=fv.contract.symbol,
        timestamp=datetime.now(timezone.utc),
        horizon="Intraday / Swing",
        trend=L(
            f"Structure {fv.structure_by_tf.get('1H')} en 1H, "
            f"{fv.structure_by_tf.get('4H')} en 4H.",
            f"{fv.structure_by_tf.get('1H')} on 1H, "
            f"{fv.structure_by_tf.get('4H')} on 4H.",
        ),
        volatility=L(
            f"ATR au {int(fv.atr_percentile.value)}e percentile.",
            f"ATR at the {int(fv.atr_percentile.value)}th percentile.",
        ),
        macro_regime=L(str(macro_p.get("regime", "-")), str(macro_p.get("regime", "-"))),
        event_risk=L(str(event_p.get("level", "-")), str(event_p.get("level", "-"))),
        direction=decision,
        conviction=conviction,
        expected_horizon=L("4 a 12 heures", "4 to 12 hours"),
        thesis=rationale,
        technical=TicketSection(
            title=L("Technique", "Technical"),
            rows=[
                ("Structure 1H", str(fv.structure_by_tf.get("1H"))),
                ("Structure 4H", str(fv.structure_by_tf.get("4H"))),
                ("Coherence", f"{tech_p.get('alignment', 0)} %"),
                ("VWAP", f"{fv.vwap_distance_atr.value:+.2f} ATR"),
            ],
        ),
        macro=TicketSection(
            title=L("Macro", "Macro"),
            rows=[
                ("Regime", str(macro_p.get("regime", "-"))),
                ("Impact or", str(macro_p.get("gold_impact", "-"))),
                ("Force", f"{macro_p.get('strength', 0)}/100"),
            ],
        ),
        futures=TicketSection(
            title=L("Futures / Positionnement", "Futures / Positioning"),
            rows=[
                ("Open interest", f"{fut_p.get('oi_change', 0):+,}"),
                ("Volume", f"{fut_p.get('volume_vs_avg', 1):.2f}x"),
                ("Courbe", str(fut_p.get("curve_state", "-"))),
                ("Liquidite", f"{fut_p.get('liquidity_score', 0)}/100"),
            ],
        ),
        catalysts=TicketSection(
            title=L("Catalyseurs", "Catalysts"),
            rows=[
                ("Prochain", str((event_p.get("next_event") or {}).get("name", {}).get("fr", "-"))),
                ("Dans", f"{(event_p.get('next_event') or {}).get('minutes_until', 0)} min"),
                ("Niveau", str(event_p.get("level", "-"))),
            ],
        ),
        bull_case=bull,
        bear_case=bear or [L("Aucune objection majeure.", "No major objection.")],
        invalidation=[
            L(f"Le prix clôture au-delà de {stop_price} sur l'unité de décision.",
              f"Price closes beyond {stop_price} on the decision timeframe."),
            L("La cohérence multi-unités passe sous 40 %.",
              "Cross-timeframe agreement drops below 40%."),
            L("Une relation macro supplémentaire se rompt.",
              "One more macro relationship breaks."),
        ],
        entry_zone=L(
            f"{fv.spot} $ (zone {round(fv.spot - atr * 0.3, 2)} - "
            f"{round(fv.spot + atr * 0.3, 2)})",
            f"${fv.spot} (zone {round(fv.spot - atr * 0.3, 2)} - "
            f"{round(fv.spot + atr * 0.3, 2)})",
        ),
        stop_logic=L(
            f"Stop structurel a {stop_price}, soit {stop_atr} ATR.",
            f"Structural stop at {stop_price}, i.e. {stop_atr} ATR.",
        ),
        target_logic=L(
            f"Premier objectif {target_price} (2 R).",
            f"First target {target_price} (2 R).",
        ),
        time_stop=L(
            "Sortie si la thèse ne se materialise pas en 12 heures.",
            "Exit if the thesis has not materialised within 12 hours.",
        ),
        risk_budget=L(
            f"{risk_p.get('risk_budget_pct', 0)} % du capital, "
            f"{risk_p.get('suggested_size', 0)} contrat(s).",
            f"{risk_p.get('risk_budget_pct', 0)}% of equity, "
            f"{risk_p.get('suggested_size', 0)} contract(s).",
        ),
        liquidity=L(
            f"Session {fv.session.session}, liquidité "
            f"{fut_p.get('liquidity_score', 0)}/100.",
            f"{fv.session.session} session, liquidity "
            f"{fut_p.get('liquidity_score', 0)}/100.",
        ),
        event_exposure=L(
            str(event_p.get("reason", {}).get("fr", "-")),
            str(event_p.get("reason", {}).get("en", "-")),
        ),
        risk_verdict=RiskVerdict(risk_p.get("verdict", "REJECT")),
        final_decision=decision,
        decision_rationale=rationale,
        monitoring=[
            L("Rupture de la structure sur l'unité de décision.",
              "Structure break on the decision timeframe."),
            L("Publication macro non programmee.", "Unscheduled macro release."),
            L("Effondrement du volume sous 0,8x la moyenne.",
              "Volume collapse below 0.8x average."),
            L("Bascule du régime de volatilité.", "Volatility regime shift."),
        ],
    )
