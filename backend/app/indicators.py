"""
Les quatre outils du système, et rien d'autre : ATR, VWAP, profil de volume,
structure de marché.

Couche 100 % déterministe (pandas / numpy). Chaque nombre affiché dans le
dashboard ou cité par le comité est calculé ici. Toutes les fonctions sont
pures : mêmes barres en entrée, mêmes chiffres en sortie, ce qui rend le
rejeu historique (et donc la mesure honnête) possible.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ==========================================================================
# ATR
# ==========================================================================
def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR de Wilder : lissage exponentiel alpha = 1/period."""
    return true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def percentile_rank(series: pd.Series, lookback: int = 2000) -> int:
    """Rang (0-100) de la dernière valeur dans son propre historique récent."""
    window = series.dropna().tail(lookback)
    if len(window) < 20:
        return 50
    return int(round((window <= window.iloc[-1]).mean() * 100))


def vol_regime(pct: int) -> str:
    if pct >= 90:
        return "EXTREME"
    if pct >= 65:
        return "EXPANDING"
    if pct <= 20:
        return "COMPRESSED"
    return "NORMAL"


# ==========================================================================
# VWAP de séance + bandes d'écart-type
# ==========================================================================
def session_labels(index: pd.DatetimeIndex, tz: str, roll_hour: int) -> pd.Series:
    """
    Date de la journée de trading de chaque barre.

    Avec roll_hour = 18 (futures CME), une barre du dimanche 18 h NY appartient
    à la séance du lundi.
    """
    local = index.tz_convert(tz)
    shifted = local + pd.Timedelta(hours=(24 - roll_hour) % 24)
    return pd.Series(shifted.date, index=index)


def session_vwap(df: pd.DataFrame, labels: pd.Series) -> pd.DataFrame:
    """
    VWAP ancrée au début de chaque séance, et son écart-type pondéré par le
    volume (bandes à 1 et 2 sigma).

    Prix typique (H+L+C)/3 : avec des barres de 15 minutes, on ne connaît pas
    la distribution des transactions à l'intérieur de la barre.
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].astype(float)
    g = labels.values
    cum_v = v.groupby(g).cumsum()
    cum_pv = (tp * v).groupby(g).cumsum()
    cum_p2v = (tp * tp * v).groupby(g).cumsum()
    safe_v = cum_v.replace(0, np.nan)
    vwap = cum_pv / safe_v
    var = (cum_p2v / safe_v - vwap * vwap).clip(lower=0)
    sd = np.sqrt(var)
    return pd.DataFrame({
        "vwap": vwap, "sd": sd,
        "u1": vwap + sd, "l1": vwap - sd,
        "u2": vwap + 2 * sd, "l2": vwap - 2 * sd,
    }, index=df.index)


# ==========================================================================
# Profil de volume
# ==========================================================================
@dataclass
class Profile:
    poc: float
    vah: float
    val: float
    bin_size: float
    edges: np.ndarray = field(repr=False)
    volume: np.ndarray = field(repr=False)
    total: float = 0.0

    def to_json(self, max_bins: int = 80) -> dict:
        lo = self.edges[:-1]
        vol = self.volume
        # Regroupe si trop de cases : le navigateur n'a pas besoin de 300 barres.
        if len(vol) > max_bins:
            k = int(np.ceil(len(vol) / max_bins))
            vol = np.add.reduceat(self.volume, np.arange(0, len(self.volume), k))
            lo = self.edges[:-1][::k]
            size = self.bin_size * k
        else:
            size = self.bin_size
        return {
            "poc": round(self.poc, 2), "vah": round(self.vah, 2),
            "val": round(self.val, 2), "bin_size": round(size, 4),
            "bins": [[round(float(p), 4), round(float(v), 1)] for p, v in zip(lo, vol)],
        }


def volume_profile(df: pd.DataFrame, bin_size: float | None = None,
                   value_area: float = 0.70) -> Profile | None:
    """
    Répartit le volume de chaque barre uniformément sur son étendue [bas, haut],
    puis calcule POC (prix de volume maximal) et zone de valeur (70 % du
    volume, construite en partant du POC vers le côté le plus chargé).

    Hypothèse assumée : volume uniforme dans la barre. C'est une
    approximation du vrai profil tick par tick ; elle est d'autant meilleure
    que les barres sont fines.
    """
    if df.empty or df["volume"].sum() <= 0:
        return None
    lo, hi = float(df["low"].min()), float(df["high"].max())
    span = hi - lo
    if span <= 0:
        return None
    if not bin_size or bin_size <= 0:
        bin_size = span / 60
    n_bins = int(np.clip(np.ceil(span / bin_size), 12, 400))
    bin_size = span / n_bins
    edges = lo + bin_size * np.arange(n_bins + 1)

    bl = df["low"].to_numpy(float)[:, None]
    bh = df["high"].to_numpy(float)[:, None]
    bh = np.where(bh - bl <= 0, bl + bin_size * 1e-6, bh)
    bv = df["volume"].to_numpy(float)[:, None]
    overlap = np.clip(np.minimum(bh, edges[None, 1:]) - np.maximum(bl, edges[None, :-1]),
                      0, None)
    vol = (overlap / (bh - bl) * bv).sum(axis=0)

    total = float(vol.sum())
    poc_i = int(np.argmax(vol))
    lo_i = hi_i = poc_i
    acc = vol[poc_i]
    while acc < value_area * total and (lo_i > 0 or hi_i < n_bins - 1):
        up = vol[hi_i + 1] if hi_i < n_bins - 1 else -1
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn
    return Profile(
        poc=float(edges[poc_i] + bin_size / 2),
        vah=float(edges[hi_i + 1]),
        val=float(edges[lo_i]),
        bin_size=float(bin_size),
        edges=edges, volume=vol, total=total,
    )


# ==========================================================================
# Structure de marché
# ==========================================================================
def swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[dict]:
    """
    Pivots fractals. Un pivot haut en i dépasse les `left` barres avant et
    n'est pas dépassé par les `right` barres après. Il n'est donc CONNU qu'en
    i + right (`known_at`) : l'utiliser avant serait du look-ahead.

    Chaque pivot est étiqueté par rapport au précédent de même nature :
    HH / LH pour les hauts, HL / LL pour les bas.
    """
    if len(df) < left + right + 1:
        return []
    h, l = df["high"], df["low"]
    lmax = h.shift(1).rolling(left).max()
    rmax = h[::-1].shift(1).rolling(right).max()[::-1]
    lmin = l.shift(1).rolling(left).min()
    rmin = l[::-1].shift(1).rolling(right).min()[::-1]
    is_h = ((h > lmax) & (h >= rmax)).to_numpy()
    is_l = ((l < lmin) & (l <= rmin)).to_numpy()

    out: list[dict] = []
    last = {"H": None, "L": None}
    hv, lv = h.to_numpy(float), l.to_numpy(float)
    for i in range(len(df)):
        for kind, flag, price in (("H", is_h[i], hv[i]), ("L", is_l[i], lv[i])):
            if not flag:
                continue
            prev = last[kind]
            if prev is None:
                label = None
            elif kind == "H":
                label = "HH" if price > prev else "LH"
            else:
                label = "HL" if price > prev else "LL"
            out.append({"i": i, "kind": kind, "price": float(price),
                        "label": label, "known_at": i + right})
            last[kind] = price
    return out


@dataclass
class Structure:
    trend: int                       # +1 haussière, -1 baissière, 0 indéterminée
    events: list[dict]               # BOS / CHoCH
    swings: list[dict]
    last_high: dict | None           # dernier pivot haut connu
    last_low: dict | None

    @property
    def label(self) -> str:
        return {1: "UPTREND", -1: "DOWNTREND"}.get(self.trend, "RANGE")


def market_structure(df: pd.DataFrame, left: int = 3, right: int = 3) -> Structure:
    """
    Machine à états de structure, en clôture (une mèche ne casse rien).

    - BOS (break of structure) : clôture au-delà du dernier pivot DANS le sens
      de la tendance -> continuation.
    - CHoCH (change of character) : clôture au-delà du dernier pivot CONTRE
      la tendance -> premier signe de retournement.

    Seuls les pivots déjà connus à la barre t sont utilisés à la barre t.
    """
    sw = swings(df, left, right)
    by_known: dict[int, list[dict]] = {}
    for s in sw:
        by_known.setdefault(s["known_at"], []).append(s)

    close = df["close"].to_numpy(float)
    trend = 0
    hi = lo = None
    hi_broken = lo_broken = True
    events: list[dict] = []
    for t in range(len(df)):
        for s in by_known.get(t, []):
            if s["kind"] == "H":
                hi, hi_broken = s, False
            else:
                lo, lo_broken = s, False
        c = close[t]
        if hi is not None and not hi_broken and c > hi["price"]:
            events.append({"i": t, "kind": "CHoCH" if trend == -1 else "BOS",
                           "dir": 1, "level": hi["price"], "from_i": hi["i"]})
            hi_broken, trend = True, 1
        if lo is not None and not lo_broken and c < lo["price"]:
            events.append({"i": t, "kind": "CHoCH" if trend == 1 else "BOS",
                           "dir": -1, "level": lo["price"], "from_i": lo["i"]})
            lo_broken, trend = True, -1
    known = [s for s in sw if s["known_at"] < len(df)]
    last_high = next((s for s in reversed(known) if s["kind"] == "H"), None)
    last_low = next((s for s in reversed(known) if s["kind"] == "L"), None)
    return Structure(trend=trend, events=events, swings=sw,
                     last_high=last_high, last_low=last_low)
