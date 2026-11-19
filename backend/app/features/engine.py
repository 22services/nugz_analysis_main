"""
Construction du feature vector + detection des candidats de setup.

Hermes, pendant le debat d'archi : "cette couche de detection deterministe EST
ton alpha. Passe plus de temps sur le detecteur de candidats que sur les prompts
des 4 analystes." C'est pour cela que ce module ne contient aucun LLM et que
chaque seuil y est explicite plutot qu'enfoui dans un prompt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.features import indicators as ind
from app.mock import fixtures
from app.schemas import (
    Direction,
    FeatureVector,
    Localized,
    MarketStructure,
    SemanticValue,
    Timeframe,
    TriggerCandidate,
    TriggerPriority,
)

# Seuils de declenchement. Explicites et versionnes avec le schema.
ATR_EXPANSION_PCT = 75        # percentile ATR au-dela duquel on parle d'expansion
LEVEL_PROXIMITY_ATR = 0.35    # "colle" a un niveau si moins de 0,35 ATR
VWAP_PROXIMITY_ATR = 0.20
MACRO_WINDOW_MINUTES = 90
COOLDOWN_MINUTES = {"5m": 15, "15m": 30, "1H": 60, "4H": 240, "1D": 720}


# --------------------------------------------------------------------------
def analyse_timeframes(market: dict[str, pd.DataFrame]) -> list[dict]:
    """Lecture déterministe de chaque unité de temps."""
    reads = []
    for tf, df in market.items():
        structure, quality = ind.classify_structure(df)
        atr_series = ind.atr(df)
        vwap = ind.session_vwap(df)
        reads.append(
            {
                "timeframe": tf,
                "structure": structure,
                "quality": quality,
                "momentum": ind.momentum_score(df),
                "atr": round(float(atr_series.iloc[-1]), 2),
                "atr_percentile": ind.atr_percentile(atr_series),
                "above_vwap": bool(df["close"].iloc[-1] > vwap.iloc[-1]),
                "vwap": round(float(vwap.iloc[-1]), 2),
                "close": round(float(df["close"].iloc[-1]), 2),
            }
        )
    return reads


def build_feature_vector(market: dict[str, pd.DataFrame]) -> FeatureVector:
    """
    Produit le JSON que les agents LLM recevront.

    Deux regles heritees du debat avec Hermes :
      - valeurs DERIVEES (distances en ATR), pas de chiffres bruts a re-deriver ;
      - chaque nombre porte son unite et son sens.
    """
    reads = analyse_timeframes(market)
    ref = market["5m"]
    spot = round(float(ref["close"].iloc[-1]), 2)
    atr5 = float(ind.atr(ref).iloc[-1]) or 1.0
    vwap5 = float(ind.session_vwap(ref).iloc[-1])

    levels = ind.key_levels(market["1H"], spot)
    resistances = [lv for lv in levels if lv["kind"] == "resistance"]
    supports = [lv for lv in levels if lv["kind"] == "support"]
    nearest_r = min(resistances, key=lambda l: l["distance_pct"], default=None)
    nearest_s = max(supports, key=lambda l: l["distance_pct"], default=None)

    by_tf = {r["timeframe"]: r for r in reads}
    alignment = ind.alignment_score(reads)
    dominant = _dominant_direction(reads)
    vwap_dist = round((spot - vwap5) / atr5, 2)

    return FeatureVector(
        as_of=datetime.now(timezone.utc),
        contract=fixtures.contract_context(),
        session=fixtures.session_context(),
        spot=spot,
        vwap_distance_atr=SemanticValue(
            value=vwap_dist,
            unit="atr",
            meaning="spot_minus_session_vwap_in_atr_units",
            direction_if_high=Direction.LONG,
        ),
        nearest_resistance_atr=SemanticValue(
            value=round((nearest_r["price"] - spot) / atr5, 2) if nearest_r else 99.0,
            unit="atr",
            meaning="distance_up_to_nearest_tested_resistance",
        ),
        nearest_support_atr=SemanticValue(
            value=round((spot - nearest_s["price"]) / atr5, 2) if nearest_s else 99.0,
            unit="atr",
            meaning="distance_down_to_nearest_tested_support",
        ),
        atr_percentile=SemanticValue(
            value=float(by_tf["5m"]["atr_percentile"]),
            unit="percentile",
            meaning="current_atr_rank_within_own_history",
        ),
        structure_by_tf={r["timeframe"]: r["structure"].value for r in reads},
        momentum_by_tf={r["timeframe"]: r["momentum"] for r in reads},
        alignment=SemanticValue(
            value=float(alignment),
            unit="pct",
            meaning="cross_timeframe_structural_agreement_weighted_by_horizon",
        ),
        extras={
            "atr_5m": SemanticValue(
                value=round(atr5, 2), unit="usd/oz", meaning="average_true_range_5m"
            ),
            "levels_count": SemanticValue(
                value=float(len(levels)), unit="count", meaning="tested_levels_in_range"
            ),
        },
        state_summary=Localized(
            fr=(
                f"Or à {spot} $. Structure dominante {dominant}, cohérence multi-UT "
                f"{alignment} %. Spot à {vwap_dist} ATR de la VWAP de session."
            ),
            en=(
                f"Gold at ${spot}. Dominant structure {dominant}, cross-timeframe "
                f"agreement {alignment}%. Spot {vwap_dist} ATR from session VWAP."
            ),
        ),
    )


def _dominant_direction(reads: list[dict]) -> str:
    up = sum(1 for r in reads if r["structure"] is MarketStructure.UPTREND)
    down = sum(1 for r in reads if r["structure"] is MarketStructure.DOWNTREND)
    if up > down:
        return "UPTREND"
    if down > up:
        return "DOWNTREND"
    return "RANGE"


# --------------------------------------------------------------------------
# Detection des candidats
# --------------------------------------------------------------------------
def detect_triggers(
    market: dict[str, pd.DataFrame],
    fv: FeatureVector,
    calendar: list | None = None,
) -> list[TriggerCandidate]:
    """
    Ne reveille le pipeline LLM que sur evenement reel.

    Garde-fous demandes par Hermes : cle de dedup (symbole + timeframe + type +
    index de barre) et cooldown par unite de temps, sinon un prix colle a un
    niveau pendant 30 minutes genere six fois le meme run.
    """
    out: list[TriggerCandidate] = []
    now = datetime.now(timezone.utc)
    sym = fv.contract.symbol

    def add(kind: str, tf: str, priority: TriggerPriority, fr: str, en: str) -> None:
        bar_index = len(market[tf])
        out.append(
            TriggerCandidate(
                kind=kind,
                priority=priority,
                dedup_key=f"{sym}:{tf}:{kind}:{bar_index}",
                timeframe=Timeframe(tf),
                detected_at=now,
                reason=Localized(fr=fr, en=en),
                cooldown_until=now + timedelta(minutes=COOLDOWN_MINUTES[tf]),
            )
        )

    # 1. Expansion de volatilite
    pct = int(fv.atr_percentile.value)
    if pct >= ATR_EXPANSION_PCT:
        add(
            "atr_expansion", "5m", TriggerPriority.HIGH,
            f"ATR au {pct}e percentile : la volatilité se détend, les mouvements portent.",
            f"ATR at the {pct}th percentile: volatility is expanding, moves carry.",
        )

    # 2. Prix colle a un niveau deja teste
    if abs(fv.nearest_resistance_atr.value) <= LEVEL_PROXIMITY_ATR:
        add(
            "level_break", "1H", TriggerPriority.HIGH,
            "Le prix testé une résistance déjà éprouvée : cassure ou rejet imminent.",
            "Price is testing a previously tested resistance: break or rejection imminent.",
        )
    if abs(fv.nearest_support_atr.value) <= LEVEL_PROXIMITY_ATR:
        add(
            "level_break", "1H", TriggerPriority.HIGH,
            "Le prix testé un support déjà éprouvé : cassure ou rebond imminent.",
            "Price is testing a previously tested support: break or bounce imminent.",
        )

    # 3. Test de VWAP
    if abs(fv.vwap_distance_atr.value) <= VWAP_PROXIMITY_ATR:
        add(
            "vwap_test", "5m", TriggerPriority.LOW,
            "Retour sur la VWAP de session : zone de décision des intervenants.",
            "Pullback into session VWAP: participants' decision zone.",
        )

    # 4. Bascule structurelle entre unites longues
    if fv.structure_by_tf.get("1H") != fv.structure_by_tf.get("4H"):
        add(
            "structure_shift", "4H", TriggerPriority.MEDIUM,
            "Désaccord de structure entre 1H et 4H : transition de régime possible.",
            "Structure disagreement between 1H and 4H: possible regime transition.",
        )

    # 5. Fenetre macro - priorite maximale
    for ev in calendar or []:
        if 0 < ev.minutes_until <= MACRO_WINDOW_MINUTES and ev.importance in ("HIGH", "CRITICAL"):
            add(
                "macro_window", "5m", TriggerPriority.CRITICAL,
                f"{ev.name.fr} dans {ev.minutes_until} min : fenêtre à risque événementiel.",
                f"{ev.name.en} in {ev.minutes_until} min: event-risk window.",
            )
            break

    out.sort(key=lambda t: t.priority.value, reverse=True)
    return out


def apply_dedup(
    candidates: list[TriggerCandidate],
    seen: dict[str, datetime],
    now: datetime | None = None,
) -> list[TriggerCandidate]:
    """
    Filtre les declencheurs deja traites ou encore en cooldown.
    Sans cela, un prix immobile sur un niveau relance le pipeline en boucle.
    """
    now = now or datetime.now(timezone.utc)
    kept = []
    for c in candidates:
        until = seen.get(c.dedup_key)
        if until and until > now:
            continue
        seen[c.dedup_key] = c.cooldown_until or now
        kept.append(c)
    return kept
