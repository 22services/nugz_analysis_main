"""
Agents 1 a 5 : la fondation et les quatre analystes.

V1 : aucun outil branche. Chaque agent derive sa lecture du feature vector
deterministe. Quand les feeds seront connectes, seule la methode `run` change ;
le contrat de sortie, lui, ne bouge pas.
"""
from __future__ import annotations

from app.agents.base import Agent, RunContext
from app.schemas import (
    AgentOutput,
    AgentStatus,
    CrossAssetRead,
    Direction,
    Evidence,
    EventPayload,
    EventRisk,
    FuturesPayload,
    Localized,
    MacroPayload,
    MacroRegime,
    MarketStatePayload,
    MarketStructure,
    ModelTier,
    PriceLevel,
    RunStage,
    TechnicalPayload,
    TimeframeRead,
    Timeframe,
    ToolSpec,
    TrendQuality,
    VolRegime,
)


def L(fr: str, en: str) -> Localized:
    return Localized(fr=fr, en=en)


# ==========================================================================
# 1. Data & Market State - la fondation
# ==========================================================================
class DataMarketStateAgent(Agent):
    """
    Deterministe par construction : zero appel LLM.

    Point tranche avec Hermes pendant le debat d'archi. Il faisait remarquer
    qu'un agent de donnees n'a aucune raison d'etre un LLM - ce serait meme une
    faute, puisque c'est precisement lui qui garantit que les chiffres sont
    justes. Il reste un agent au sens architectural : mandat propre, contrat de
    sortie propre, et surtout le droit d'arreter tout le pipeline.
    """

    id = "data_market_state"
    order = 1
    stage = RunStage.DATA
    model_tier = ModelTier.NONE
    can_veto = True

    name = L("Données & État du marché", "Data & Market State")
    role = L("La fondation", "The foundation")
    mandate = L(
        "Alimente tous les autres agents et refuse de lancer l'analyse si les "
        "données sont périmées ou incohérentes. Conserve pour chaque donnée sa "
        "source, son horodatage et sa fraîcheur.",
        "Feeds every other agent and refuses to launch the analysis if data is "
        "stale or inconsistent. Keeps source, timestamp and freshness for every "
        "input.",
    )
    plain = L(
        "Il vérifie que les informations sont à jour avant que quiconque donné "
        "son avis. Si une donnée est trop vieille, il arrête tout - mieux vaut "
        "ne rien faire que décider sur des chiffres faux.",
        "It checks the information is current before anyone gives an opinion. If "
        "something is too old it stops everything - better to do nothing than to "
        "decide on wrong numbers.",
    )
    tools = [
        ToolSpec(name="OHLCV GC front-month", provider="databento | polygon",
                 purpose=L("Prix et volume du contrat actif", "Active contract price and volume")),
        ToolSpec(name="XAU/USD spot", provider="twelvedata",
                 purpose=L("Or au comptant", "Spot gold")),
        ToolSpec(name="DXY / Treasuries / taux reels", provider="fred",
                 purpose=L("Variables macro de référence", "Reference macro variables")),
        ToolSpec(name="Calendrier des rolls CME", provider="cme",
                 purpose=L("Échéances et bascule de contrat", "Expiries and contract roll")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        fv = ctx.features
        sources = ctx.market["sources"]
        stale = [s for s in sources if s.is_stale]
        all_fresh = not stale

        halt = bool(stale)
        halt_reason = None
        if halt:
            names = ", ".join(s.name for s in stale)
            halt_reason = L(
                f"Analyse interrompue : {len(stale)} source(s) périmée(s) - {names}.",
                f"Analysis halted: {len(stale)} stale source(s) - {names}.",
            )
            ctx.halted = True
            ctx.halt_reason = halt_reason

        payload = MarketStatePayload(
            instrument="GC",
            contract=fv.contract.symbol,
            spot=fv.spot,
            change_pct=round(ctx.market["change_pct"], 2),
            session=fv.session.session,
            sources=sources,
            all_fresh=all_fresh,
            halt=halt,
            halt_reason=halt_reason,
            roll_warning=fv.contract.roll_warning,
        )

        warnings = []
        if fv.contract.roll_warning:
            warnings.append(fv.contract.roll_warning)
        if not fv.session.is_liquid_hours:
            warnings.append(L(
                "Hors heures liquides : écarts plus larges, niveaux moins "
                "fiables.",
                "Outside liquid hours: wider spreads, less reliable levels.",
            ))

        return AgentOutput(
            agent_id=self.id,
            status=AgentStatus.BLOCKED if halt else AgentStatus.DONE,
            headline=halt_reason or L(
                f"{len(sources)} sources vérifiées, toutes dans leur fenêtre de fraîcheur.",
                f"{len(sources)} sources checked, all within their freshness window.",
            ),
            detail=L(
                f"Contrat {fv.contract.symbol}, session {fv.session.session}, "
                f"roll dans {fv.contract.days_to_roll} jours. Série utilisée : "
                f"{fv.contract.series_type}.",
                f"Contract {fv.contract.symbol}, {fv.session.session} session, "
                f"roll in {fv.contract.days_to_roll} days. Series used: "
                f"{fv.contract.series_type}.",
            ),
            evidence=[
                Evidence(
                    label=L("Sources fraîches", "Fresh sources"),
                    value=f"{len(sources) - len(stale)}/{len(sources)}",
                    reading=L(
                        "Toutes les données sont dans leur fenêtre." if all_fresh
                        else "Certaines données ont dépassé leur durée de validité.",
                        "All inputs are within their window." if all_fresh
                        else "Some inputs exceeded their validity window.",
                    ),
                    weight=5,
                    supports=Direction.NEUTRAL,
                ),
            ],
            warnings=warnings,
            payload=payload.model_dump(mode="json"),
        )


# ==========================================================================
# 2. Technical & Market Structure - le trader technique
# ==========================================================================
class TechnicalAgent(Agent):
    """
    Modele economique, sortie contrainte par schema.

    Hermes proposait de supprimer le LLM ici puisque la structure HH/HL est
    calculable. J'ai maintenu un LLM mais bon marche : les chiffres sont bien
    deterministes, en revanche ce que le CIO consomme c'est la LECTURE
    cross-timeframe et la detection de contradiction interne. Supprimer cette
    couche revient a deplacer le travail sur l'agent le plus cher.
    """

    id = "technical"
    order = 2
    stage = RunStage.ANALYSIS
    model_tier = ModelTier.CHEAP

    name = L("Technique & Structure", "Technical & Market Structure")
    role = L("Le trader technique", "The technical trader")
    mandate = L(
        "Spécialiste de l'intraday et du swing sur 5m / 15m / 1H / 4H / Daily. "
        "plutôt que d'empiler vingt-cinq indicateurs, il rend une sortie "
        "normalisee : Direction, Conviction, Horizon, Evidence, Niveaux, "
        "Invalidation.",
        "Intraday and swing specialist across 5m / 15m / 1H / 4H / Daily. Rather "
        "than stacking twenty-five indicators, it returns a normalised output: "
        "Direction, Conviction, Horizon, Evidence, Levels, Invalidation.",
    )
    plain = L(
        "Il lit le graphique : est-ce que le prix monte, descend ou tourne en "
        "rond ? Et a quel prix son scénario devient faux.",
        "It reads the chart: is price rising, falling or going nowhere? And at "
        "what price its scenario becomes wrong.",
    )
    tools = [
        ToolSpec(name="Serie OHLCV multi-UT", provider="internal",
                 purpose=L("Structure, momentum, ATR, VWAP", "Structure, momentum, ATR, VWAP")),
        ToolSpec(name="Profil de volume", provider="databento",
                 purpose=L("POC et zones de valeur", "POC and value areas")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        fv = ctx.features
        reads_raw = ctx.market["reads"]

        reads = [
            TimeframeRead(
                timeframe=Timeframe(r["timeframe"]),
                structure=r["structure"],
                quality=r["quality"],
                momentum=r["momentum"],
                above_vwap=r["above_vwap"],
                atr=r["atr"],
                atr_percentile=r["atr_percentile"],
                note=_tf_note(r),
            )
            for r in reads_raw
        ]

        up = sum(1 for r in reads if r.structure is MarketStructure.UPTREND)
        down = sum(1 for r in reads if r.structure is MarketStructure.DOWNTREND)
        alignment = int(fv.alignment.value)

        if up > down:
            direction = Direction.LONG
        elif down > up:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL

        # La conviction suit la coherence multi-UT, pas le nombre d'indicateurs.
        conviction = int(min(95, 25 + alignment * 0.55 + abs(up - down) * 6))
        if direction is Direction.NEUTRAL:
            conviction = min(conviction, 35)

        vol = _vol_regime(int(fv.atr_percentile.value))
        levels = [
            PriceLevel(
                label=L(
                    f"{'Résistance' if lv['kind'] == 'resistance' else 'Support'} "
                    f"({lv['touches']} touches)",
                    f"{lv['kind'].capitalize()} ({lv['touches']} touches)",
                ),
                price=lv["price"],
                kind=lv["kind"],
                distance_pct=lv["distance_pct"],
                touches=lv["touches"],
            )
            for lv in ctx.market["levels"]
        ]

        atr5 = fv.extras["atr_5m"].value
        invalidation = None
        if direction is not Direction.NEUTRAL and levels:
            sign = -1 if direction is Direction.LONG else 1
            inv_price = round(fv.spot + sign * atr5 * 1.5, 2)
            invalidation = PriceLevel(
                label=L("Invalidation structurelle", "Structural invalidation"),
                price=inv_price,
                kind="invalidation",
                distance_pct=round((inv_price - fv.spot) / fv.spot * 100, 2),
            )

        evidence = [
            Evidence(
                label=L("Cohérence multi-unités", "Cross-timeframe agreement"),
                value=f"{alignment} %",
                reading=L(
                    "Les unités de temps racontent la même histoire."
                    if alignment >= 60 else
                    "Les unités de temps se contredisent : signal peu fiable.",
                    "Timeframes tell the same story." if alignment >= 60 else
                    "Timeframes contradict each other: low-reliability signal.",
                ),
                weight=5,
                supports=direction,
            ),
            Evidence(
                label=L("Position vs VWAP de session", "Position vs session VWAP"),
                value=f"{fv.vwap_distance_atr.value:+.2f} ATR",
                reading=L(
                    "Le prix se traite au-dessus du prix moyen pondéré : les "
                    "acheteurs ont la main."
                    if fv.vwap_distance_atr.value > 0 else
                    "Le prix se traite sous le prix moyen pondéré : les vendeurs "
                    "ont la main.",
                    "Price trades above the volume-weighted average: buyers in "
                    "control." if fv.vwap_distance_atr.value > 0 else
                    "Price trades below the volume-weighted average: sellers in "
                    "control.",
                ),
                weight=3,
                supports=Direction.LONG if fv.vwap_distance_atr.value > 0 else Direction.SHORT,
            ),
            Evidence(
                label=L("Régime de volatilité", "Volatility regime"),
                value=f"{int(fv.atr_percentile.value)}e percentile",
                reading=_vol_reading(vol),
                weight=4,
                supports=Direction.NEUTRAL,
            ),
        ]

        warnings = []
        if alignment < 40:
            warnings.append(L(
                "Structure incohérente entre unités de temps : le signal "
                "technique est faible, quelle que soit la conviction affichee.",
                "Incoherent structure across timeframes: the technical signal is "
                "weak regardless of the conviction shown.",
            ))

        payload = TechnicalPayload(
            reads=reads,
            alignment=alignment,
            vol_regime=vol,
            key_levels=levels,
            invalidation=invalidation,
            setup_type=_setup_type(ctx, direction),
        )

        return AgentOutput(
            agent_id=self.id,
            direction=direction,
            conviction=conviction,
            horizon=L("4 a 12 heures", "4 to 12 hours"),
            headline=L(
                f"{_dir_fr(direction)} - structure {alignment} % cohérente sur "
                f"{len(reads)} unités de temps.",
                f"{direction.value} - structure {alignment}% coherent across "
                f"{len(reads)} timeframes.",
            ),
            detail=L(
                f"{up} unité(s) haussière(s), {down} baissière(s). Volatilité au "
                f"{int(fv.atr_percentile.value)}e percentile.",
                f"{up} bullish timeframe(s), {down} bearish. Volatility at the "
                f"{int(fv.atr_percentile.value)}th percentile.",
            ),
            evidence=evidence,
            warnings=warnings,
            payload=payload.model_dump(mode="json"),
        )


def _tf_note(r: dict) -> Localized:
    s = {
        MarketStructure.UPTREND: ("sommets et creux ascendants", "higher highs and higher lows"),
        MarketStructure.DOWNTREND: ("sommets et creux descendants", "lower highs and lower lows"),
        MarketStructure.RANGE: ("bornee, sans direction", "range-bound, directionless"),
        MarketStructure.TRANSITION: ("structure cassee, pas encore reformee", "structure broken, not yet reformed"),
    }[r["structure"]]
    return L(f"{r['timeframe']} : {s[0]}, momentum {r['momentum']:+d}.",
             f"{r['timeframe']}: {s[1]}, momentum {r['momentum']:+d}.")


def _vol_regime(pct: int) -> VolRegime:
    if pct >= 90:
        return VolRegime.EXTREME
    if pct >= 65:
        return VolRegime.EXPANDING
    if pct <= 20:
        return VolRegime.COMPRESSED
    return VolRegime.NORMAL


def _vol_reading(v: VolRegime) -> Localized:
    return {
        VolRegime.COMPRESSED: L(
            "Volatilité comprimée : les mouvements portent peu, mais une "
            "expansion se prépare souvent dans ces conditions.",
            "Compressed volatility: moves carry little, though expansion often "
            "builds in these conditions."),
        VolRegime.NORMAL: L("Volatilité normale, rien d'anormal a signaler.",
                            "Normal volatility, nothing unusual."),
        VolRegime.EXPANDING: L(
            "Volatilité en expansion : les stops doivent être plus larges et la"
            " taille réduite en conséquence.",
            "Expanding volatility: stops must be wider and size reduced accordingly."),
        VolRegime.EXTREME: L(
            "Volatilité extrême : environnement hostile, le risque de balayage "
            "des stops est élevé.",
            "Extreme volatility: hostile environment, stop-hunt risk is high."),
    }[v]


def _setup_type(ctx: RunContext, direction: Direction) -> Localized:
    kinds = {t.kind for t in ctx.market.get("triggers", [])}
    if "level_break" in kinds:
        return L("Cassure de niveau testé", "Tested-level breakout")
    if "vwap_test" in kinds:
        return L("Retour à la moyenne sur VWAP", "Mean reversion into VWAP")
    if "atr_expansion" in kinds:
        return L("Expansion de volatilité", "Volatility expansion")
    if direction is Direction.NEUTRAL:
        return L("Aucun setup identifie", "No setup identified")
    return L("Suivi de tendance", "Trend continuation")


def _dir_fr(d: Direction) -> str:
    return {
        Direction.LONG: "HAUSSIER", Direction.SHORT: "BAISSIER",
        Direction.NEUTRAL: "NEUTRE", Direction.NO_TRADE: "PAS DE TRADE",
    }[d]


# ==========================================================================
# 3. Macro & Cross-Asset - le cerveau macro de l'or
# ==========================================================================
class MacroAgent(Agent):
    """Modèle de raisonnement : il lit du texte et arbitre des relations instables."""

    id = "macro"
    order = 3
    stage = RunStage.ANALYSIS
    model_tier = ModelTier.STRONG

    name = L("Macro & Cross-Asset", "Macro & Cross-Asset")
    role = L("Le cerveau macro de l'or", "The gold macro brain")
    mandate = L(
        "Surveille le dollar, les taux nominaux et réels, les Treasuries, les "
        "anticipations Fed, l'inflation et les conditions risk-on / risk-off, "
        "puis mesure si les relations historiques sont effectivement actives "
        "dans le régime actuel.",
        "Watches the dollar, nominal and real rates, Treasuries, Fed "
        "expectations, inflation and risk-on / risk-off conditions, then "
        "measures whether historical relationships are actually active in the "
        "current regime.",
    )
    plain = L(
        "L'or réagit surtout au dollar et aux taux d'intérêt. Cet agent vérifie"
        " si ces liens habituels fonctionnent en ce moment - parfois ils se "
        "cassent, et c'est la que les erreurs arrivent.",
        "Gold mostly reacts to the dollar and interest rates. This agent checks "
        "whether those usual links are working right now - sometimes they break, "
        "and that is where mistakes happen.",
    )
    tools = [
        ToolSpec(name="FRED (DXY, DGS10, DFII10)", provider="fred",
                 purpose=L("Taux nominaux et réels", "Nominal and real rates")),
        ToolSpec(name="Anticipations Fed", provider="apify",
                 purpose=L("Probabilités implicites de taux", "Implied rate probabilities")),
        ToolSpec(name="Flux news macro", provider="apify",
                 purpose=L("Contexte qualitatif", "Qualitative context")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        macro = ctx.market["macro"]
        cross = [CrossAssetRead(**c) for c in macro["cross_assets"]]

        broken = [c for c in cross if not c.relationship_active]
        supportive = sum(1 for c in cross if c.impact_on_gold is Direction.LONG)
        adverse = sum(1 for c in cross if c.impact_on_gold is Direction.SHORT)

        impact = (Direction.LONG if supportive > adverse
                  else Direction.SHORT if adverse > supportive
                  else Direction.NEUTRAL)

        # Une relation cassee retire de la force au signal macro.
        strength = int(max(0, min(95, abs(supportive - adverse) * 22 + 30 - len(broken) * 15)))

        contradictions = [
            L(f"{c.asset} : la corrélation habituelle ({c.normal_correlation:+.2f}) "
              f"ne tient pas actuellement ({c.live_correlation:+.2f}).",
              f"{c.asset}: the usual correlation ({c.normal_correlation:+.2f}) is "
              f"not holding right now ({c.live_correlation:+.2f}).")
            for c in broken
        ]

        payload = MacroPayload(
            regime=MacroRegime(macro["regime"]),
            gold_impact=impact,
            strength=strength,
            cross_assets=cross,
            contradictions=contradictions,
            fed_expectation=L(macro["fed_fr"], macro["fed_en"]),
        )

        evidence = [
            Evidence(
                label=L(c.asset, c.asset_en or c.asset),
                value=f"{c.value} ({c.change})",
                reading=L(
                    f"Corrélation vivante {c.live_correlation:+.2f} contre "
                    f"{c.normal_correlation:+.2f} en temps normal - "
                    f"{'relation active' if c.relationship_active else 'relation rompue'}.",
                    f"Live correlation {c.live_correlation:+.2f} vs "
                    f"{c.normal_correlation:+.2f} normally - "
                    f"{'relationship active' if c.relationship_active else 'relationship broken'}.",
                ),
                weight=4 if c.relationship_active else 2,
                supports=c.impact_on_gold,
            )
            for c in cross
        ]

        warnings = []
        if broken:
            warnings.append(L(
                f"{len(broken)} relation(s) historique(s) rompue(s) : le "
                "raisonnement macro habituel ne s'applique pas tel quel.",
                f"{len(broken)} historical relationship(s) broken: the usual macro "
                "reasoning does not apply as-is.",
            ))

        return AgentOutput(
            agent_id=self.id,
            direction=impact,
            conviction=strength,
            horizon=L("1 a 5 jours", "1 to 5 days"),
            headline=L(
                f"Régime {macro['regime']} - impact {_dir_fr(impact)} sur l'or, "
                f"force {strength}/100.",
                f"{macro['regime']} regime - {impact.value} impact on gold, "
                f"strength {strength}/100.",
            ),
            detail=L(macro["fed_fr"], macro["fed_en"]),
            evidence=evidence,
            warnings=warnings,
            payload=payload.model_dump(mode="json"),
        )


# ==========================================================================
# 4. Futures & Positioning - specifique au GC
# ==========================================================================
class FuturesPositioningAgent(Agent):
    """Ce qui differencie le système d'un bot qui regarde TradingView."""

    id = "futures"
    order = 4
    stage = RunStage.ANALYSIS
    model_tier = ModelTier.CHEAP

    name = L("Futures & Positionnement", "Futures & Positioning")
    role = L("Le spécialiste du contrat GC", "The GC contract specialist")
    mandate = L(
        "Analyse l'open interest, le volume, la base spot/future, la courbe GC,"
        " les calendar spreads, la liquidité et le positionnement disponible. "
        "Pour du swing il peut intégrer le COT ; en intraday il ne doit jamais "
        "traiter une donnée publiée avec retard comme si elle decrivait le "
        "positionnement instantané.",
        "Analyses open interest, volume, spot/futures basis, the GC curve, "
        "calendar spreads, liquidity and available positioning. For swing it may "
        "use COT; intraday it must never treat lagged data as if it described "
        "instantaneous positioning.",
    )
    plain = L(
        "Il regarde qui achete et qui vend réellement sur le marché à terme, et"
        " si de l'argent frais entre réellement dans le mouvement ou s'il ne "
        "s'agit que de positions qui se debouclent.",
        "It looks at who is actually buying and selling in the futures market, "
        "and whether fresh money is really entering the move or positions are "
        "merely being unwound.",
    )
    tools = [
        ToolSpec(name="Open interest / volume CME", provider="databento",
                 purpose=L("Flux réel sur le contrat", "Real contract flow")),
        ToolSpec(name="Courbe GC & calendar spreads", provider="databento",
                 purpose=L("Structure à terme", "Term structure")),
        ToolSpec(name="COT (CFTC)", provider="apify",
                 purpose=L("Positionnement hebdomadaire, publié avec retard",
                           "Weekly positioning, published with a lag")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        f = ctx.market["futures"]
        oi_change, vol_ratio = f["oi_change"], f["volume_vs_avg"]
        price_up = ctx.market["change_pct"] > 0

        # Lecture classique open interest / prix.
        if oi_change > 0 and price_up:
            signal = L("Open interest en hausse avec le prix : de l'argent "
                       "frais entre à l'achat, le mouvement est soutenu.",
                       "Open interest rising with price: fresh money entering long, "
                       "the move is supported.")
            direction = Direction.LONG
        elif oi_change > 0 and not price_up:
            signal = L("Open interest en hausse avec un prix qui baisse : de "
                       "nouvelles positions vendeuses s'installent.",
                       "Open interest rising with falling price: new short "
                       "positions are being established.")
            direction = Direction.SHORT
        elif oi_change < 0 and price_up:
            signal = L("Open interest en baisse avec un prix qui monte : ce sont "
                       "des rachats de vendeurs, pas de l'achat convaincu. "
                       "Mouvement fragile.",
                       "Open interest falling with rising price: this is short "
                       "covering, not conviction buying. Fragile move.")
            direction = Direction.NEUTRAL
        else:
            signal = L("Open interest en baisse avec le prix : liquidation de "
                       "positions acheteuses, pression vendeuse sans conviction.",
                       "Open interest falling with price: long liquidation, "
                       "selling pressure without conviction.")
            direction = Direction.NEUTRAL

        conviction = int(min(90, 30 + abs(oi_change) / 400 + (vol_ratio - 1) * 40))
        if direction is Direction.NEUTRAL:
            conviction = min(conviction, 40)

        payload = FuturesPayload(
            volume=f["volume"],
            volume_vs_avg=vol_ratio,
            open_interest=f["open_interest"],
            oi_change=oi_change,
            oi_price_signal=signal,
            basis=f["basis"],
            curve_state=f["curve_state"],
            calendar_spread=f["calendar_spread"],
            liquidity_score=f["liquidity_score"],
            cot_net_positioning=f["cot_net"],
            cot_as_of=f["cot_as_of"],
            cot_lag_warning=L(
                f"Donnée COT datée de {f['cot_age_days']} jours. Elle décrit le "
                "positionnement passe, jamais le positionnement actuel - a ne pas "
                "utiliser pour une décision intraday.",
                f"COT data is {f['cot_age_days']} days old. It describes past "
                "positioning, never current positioning - not to be used for an "
                "intraday decision.",
            ),
        )

        evidence = [
            Evidence(
                label=L("Open interest", "Open interest"),
                value=f"{oi_change:+,} contrats",
                reading=signal,
                weight=5,
                supports=direction,
            ),
            Evidence(
                label=L("Volume vs moyenne", "Volume vs average"),
                value=f"{vol_ratio:.2f}x",
                reading=L(
                    "Volume au-dessus de la normale : le mouvement est validé par "
                    "les échanges." if vol_ratio > 1.15 else
                    "Volume insuffisant pour valider une cassure.",
                    "Above-normal volume: the move is validated by activity."
                    if vol_ratio > 1.15 else
                    "Volume too thin to validate a breakout.",
                ),
                weight=4,
                supports=direction if vol_ratio > 1.15 else Direction.NEUTRAL,
            ),
            Evidence(
                label=L("Base spot / future", "Spot / futures basis"),
                value=f"{f['basis']:+.2f} $/oz",
                reading=L(
                    f"Courbe en {f['curve_state'].lower()}.",
                    f"Curve in {f['curve_state'].lower()}.",
                ),
                weight=2,
                supports=Direction.NEUTRAL,
            ),
        ]

        warnings = [payload.cot_lag_warning]
        if vol_ratio < 0.9:
            warnings.append(L(
                "Volume sous la moyenne : toute cassure observée dans ces "
                "conditions est suspecte.",
                "Below-average volume: any breakout seen in these conditions is "
                "suspect.",
            ))

        return AgentOutput(
            agent_id=self.id,
            direction=direction,
            conviction=conviction,
            horizon=L("Intraday", "Intraday"),
            headline=L(
                f"OI {oi_change:+,} contrats, volume {vol_ratio:.2f}x la moyenne.",
                f"OI {oi_change:+,} contracts, volume {vol_ratio:.2f}x average.",
            ),
            detail=signal,
            evidence=evidence,
            warnings=warnings,
            payload=payload.model_dump(mode="json"),
        )


# ==========================================================================
# 5. Event & Catalyst - "qu'est-ce qui peut faire exploser mon trade ?"
# ==========================================================================
class EventCatalystAgent(Agent):
    """
    Un setup technique magnifique trois minutes avant une publication majeure
    n'a pas le meme profil de risque que le meme setup un jour sans catalyseur.
    """

    id = "event"
    order = 5
    stage = RunStage.ANALYSIS
    model_tier = ModelTier.STRONG

    name = L("Événements & Catalyseurs", "Event & Catalyst")
    role = L("Qu'est-ce qui peut faire exploser mon trade ?",
             "What can blow up my trade?")
    mandate = L(
        "Vérifie le calendrier avant chaque décision et classe les événements "
        "proches : FOMC, CPI, NFP, PCE, discours Fed. Rend NORMAL, ELEVATED ou "
        "HIGH EVENT RISK avec le prochain événement, son heure, les variables "
        "exposées et la raison du risque.",
        "Checks the calendar before every decision and ranks nearby events: "
        "FOMC, CPI, NFP, PCE, Fed speakers. Returns NORMAL, ELEVATED or HIGH "
        "EVENT RISK with the next event, its time, exposed variables and the "
        "reason for the risk.",
    )
    plain = L(
        "Il regarde l'agenda economique. Si une annonce importante tombe dans "
        "quelques minutes, le prix peut bouger violemment pour des raisons qui "
        "n'ont rien a voir avec le graphique.",
        "It checks the economic calendar. If a major release is due in minutes, "
        "price can move violently for reasons that have nothing to do with the "
        "chart.",
    )
    tools = [
        ToolSpec(name="Calendrier macro", provider="apify",
                 purpose=L("Heures et consensus des publications",
                           "Release times and consensus")),
        ToolSpec(name="Fil de news", provider="apify",
                 purpose=L("Catalyseurs non programmes", "Unscheduled catalysts")),
    ]

    async def run(self, ctx: RunContext) -> AgentOutput:
        events = ctx.market["calendar"]
        upcoming = sorted(events, key=lambda e: e.minutes_until)
        nxt = upcoming[0] if upcoming else None

        level = EventRisk.NORMAL
        blackout = False
        if nxt:
            critical = nxt.importance in ("HIGH", "CRITICAL")
            if nxt.minutes_until <= 15 and critical:
                level, blackout = EventRisk.HIGH, True
            elif nxt.minutes_until <= 120 and critical:
                level = EventRisk.HIGH
            elif nxt.minutes_until <= 360 and critical:
                level = EventRisk.ELEVATED
            elif nxt.minutes_until <= 60:
                level = EventRisk.ELEVATED

        reason = L("Aucun catalyseur majeur dans la fenêtre de trade.",
                   "No major catalyst within the trade window.")
        if nxt:
            reason = L(
                f"{nxt.name.fr} dans {_hm_fr(nxt.minutes_until)}. Variables "
                f"exposées : {_join(nxt.exposed_variables, 'fr')}.",
                f"{nxt.name.en} in {_hm_en(nxt.minutes_until)}. Exposed "
                f"variables: {_join(nxt.exposed_variables, 'en')}.",
            )

        payload = EventPayload(
            level=level,
            next_event=nxt,
            upcoming=upcoming[:5],
            reason=reason,
            blackout_active=blackout,
        )

        warnings = []
        if blackout:
            warnings.append(L(
                "Fenêtre de black-out : publication majeure imminente. Ouvrir "
                "une position maintenant revient a parier sur le chiffre, pas "
                "sur le setup.",
                "Black-out window: major release imminent. Opening a position now "
                "means betting on the number, not on the setup.",
            ))

        return AgentOutput(
            agent_id=self.id,
            direction=Direction.NEUTRAL,
            conviction=None,
            horizon=L("Jusqu'au prochain événement", "Until the next event"),
            headline=L(
                {EventRisk.NORMAL: "Risque événementiel normal.",
                 EventRisk.ELEVATED: "Risque événementiel élevé.",
                 EventRisk.HIGH: "RISQUE ÉVÉNEMENTIEL MAJEUR."}[level],
                {EventRisk.NORMAL: "Normal event risk.",
                 EventRisk.ELEVATED: "Elevated event risk.",
                 EventRisk.HIGH: "HIGH EVENT RISK."}[level],
            ),
            detail=reason,
            evidence=[
                Evidence(
                    label=e.name,
                    value=_hm_fr(e.minutes_until),
                    reading=L(
                        f"Importance {e.importance}. Touche : "
                        f"{_join(e.exposed_variables, 'fr')}."
                        + (f" Consensus {e.consensus}." if e.consensus else ""),
                        f"{e.importance} importance. Affects: "
                        f"{_join(e.exposed_variables, 'en')}."
                        + (f" Consensus {e.consensus}." if e.consensus else ""),
                    ),
                    weight=5 if e.importance == "CRITICAL" else 3,
                    supports=Direction.NEUTRAL,
                )
                for e in upcoming[:4]
            ],
            warnings=warnings,
            payload=payload.model_dump(mode="json"),
        )


def _join(items: list[Localized], lang: str) -> str:
    """Joint des libellés bilingues dans la langue demandée."""
    return ", ".join(getattr(i, lang) for i in items)


def _hm_fr(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    if h < 24:
        return f"{h} h {m:02d}"
    return f"{h // 24} j {h % 24} h"


def _hm_en(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    if h < 24:
        return f"{h}h{m:02d}"
    return f"{h // 24}d {h % 24}h"
