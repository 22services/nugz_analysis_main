"""
Couche deterministe. AUCUN LLM ici.

C'est le point d'architecture le plus important du systeme: tout nombre affiche
dans le dashboard ou cite par un agent est calcule ici, en pandas/numpy.
Les agents LLM recoivent ces valeurs deja chiffrees et se contentent de les
interpreter. Un LLM a qui l'on demande de calculer un ATR hallucine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.schemas import MarketStructure, TrendQuality, VolRegime


# --------------------------------------------------------------------------
# Volatilite
# --------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR de Wilder (lissage exponentiel alpha = 1/period)."""
    return true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def atr_percentile(series: pd.Series, lookback: int = 200) -> int:
    """Ou se situe l'ATR actuel dans son propre historique recent."""
    window = series.dropna().tail(lookback)
    if len(window) < 20:
        return 50
    return int(round((window <= window.iloc[-1]).mean() * 100))


def vol_regime(pct: int) -> VolRegime:
    if pct >= 90:
        return VolRegime.EXTREME
    if pct >= 65:
        return VolRegime.EXPANDING
    if pct <= 20:
        return VolRegime.COMPRESSED
    return VolRegime.NORMAL


# --------------------------------------------------------------------------
# VWAP
# --------------------------------------------------------------------------
def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP ancre au debut de chaque journee de trading."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.normalize()
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum().replace(0, np.nan)
    return pv / vol


# --------------------------------------------------------------------------
# Structure de marche: HH / HL / LH / LL
# --------------------------------------------------------------------------
def swing_points(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    """
    Detection fractale des swings. Un pivot haut est un plus-haut entoure de
    `left` barres plus basses a gauche et `right` a droite. Le decalage `right`
    signifie qu'un swing n'est confirme qu'apres coup - c'est voulu, sinon on
    introduit du look-ahead bias.
    """
    highs, lows = df["high"], df["low"]
    win = left + right + 1
    is_high = highs == highs.rolling(win, center=True).max()
    is_low = lows == lows.rolling(win, center=True).min()
    return pd.DataFrame({"swing_high": highs.where(is_high), "swing_low": lows.where(is_low)})


def classify_structure(df: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[MarketStructure, TrendQuality]:
    """Lit la séquence des deux derniers swings hauts et bas."""
    sw = swing_points(df, left, right)
    hi = sw["swing_high"].dropna().tail(3).tolist()
    lo = sw["swing_low"].dropna().tail(3).tolist()

    if len(hi) < 2 or len(lo) < 2:
        return MarketStructure.TRANSITION, TrendQuality.CHOPPY

    higher_high, higher_low = hi[-1] > hi[-2], lo[-1] > lo[-2]
    lower_high, lower_low = hi[-1] < hi[-2], lo[-1] < lo[-2]

    if higher_high and higher_low:
        structure = MarketStructure.UPTREND
    elif lower_high and lower_low:
        structure = MarketStructure.DOWNTREND
    elif (higher_high and lower_low) or (lower_high and higher_low):
        structure = MarketStructure.RANGE
    else:
        structure = MarketStructure.TRANSITION

    # Qualite: une tendance propre progresse par impulsions nettes.
    if structure in (MarketStructure.UPTREND, MarketStructure.DOWNTREND):
        legs = [abs(hi[-1] - lo[-1]), abs(hi[-2] - lo[-2])]
        ratio = min(legs) / max(legs) if max(legs) else 0.0
        if ratio < 0.35:
            quality = TrendQuality.EXHAUSTED   # la derniere jambe s'essouffle
        elif ratio > 0.7:
            quality = TrendQuality.CLEAN
        else:
            quality = TrendQuality.CHOPPY
    else:
        quality = TrendQuality.CHOPPY

    return structure, quality


# --------------------------------------------------------------------------
# Momentum
# --------------------------------------------------------------------------
def momentum_score(df: pd.DataFrame, fast: int = 12, slow: int = 26) -> int:
    """
    Momentum normalise -100..+100. On divise l'ecart des moyennes par l'ATR
    pour que le score soit comparable d'un regime de volatilite a l'autre.
    """
    close = df["close"]
    spread = close.ewm(span=fast).mean() - close.ewm(span=slow).mean()
    scale = atr(df).iloc[-1]
    if not scale or np.isnan(scale):
        return 0
    return int(np.clip(spread.iloc[-1] / scale * 50, -100, 100))


# --------------------------------------------------------------------------
# Niveaux
# --------------------------------------------------------------------------
def key_levels(df: pd.DataFrame, spot: float, max_levels: int = 6) -> list[dict]:
    """
    Regroupe les swings proches en zones et compte les touches.
    Plus une zone a ete testee, plus elle compte.
    """
    sw = swing_points(df)
    raw = pd.concat([sw["swing_high"].dropna(), sw["swing_low"].dropna()]).tolist()
    if not raw:
        return []

    tolerance = float(atr(df).iloc[-1]) * 0.5
    clusters: list[list[float]] = []
    for price in sorted(raw):
        if clusters and price - clusters[-1][-1] <= tolerance:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    levels = [
        {
            "price": round(float(np.mean(c)), 2),
            "touches": len(c),
            "kind": "resistance" if np.mean(c) > spot else "support",
            "distance_pct": round((float(np.mean(c)) - spot) / spot * 100, 2),
        }
        for c in clusters
    ]
    # On garde les zones les plus testees, puis les plus proches du spot.
    levels.sort(key=lambda lv: (-lv["touches"], abs(lv["distance_pct"])))
    return levels[:max_levels]


def alignment_score(reads: list[dict]) -> int:
    """
    Coherence multi-timeframe 0..100. Les unites longues pesent plus lourd:
    un 5m qui contredit le 4H n'a pas le meme poids que l'inverse.
    """
    weights = {"5m": 1, "15m": 2, "1H": 3, "4H": 4, "1D": 5}
    total = signed = 0
    for r in reads:
        w = weights.get(r["timeframe"], 1)
        total += w
        if r["structure"] == MarketStructure.UPTREND:
            signed += w
        elif r["structure"] == MarketStructure.DOWNTREND:
            signed -= w
    return int(round(abs(signed) / total * 100)) if total else 0
