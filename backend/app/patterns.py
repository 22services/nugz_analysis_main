"""
Détection de patterns + leur mesure statistique.

Un pattern dessiné sur un graphique n'est pas un edge. Chaque type de
pattern est donc mesuré sur l'historique chargé, contre un MODÈLE NUL :
« en prenant une barre au hasard, à quelle fréquence le prix avance-t-il
dans ce sens sur le même horizon ? ». Un pattern qui fait 52 % quand le
hasard fait 51 % n'apporte rien, même s'il « marche souvent ».

Étiquettes (jamais « VALIDÉ » ici : 60 jours de données Yahoo ne permettent
pas un walk-forward sur plusieurs régimes) :
  - INSUFFICIENT : moins de 30 événements indépendants ;
  - NOT_PROVEN   : ne bat pas le hasard de façon robuste ;
  - PLAUSIBLE    : borne basse de l'IC corrigé pour tests multiples
                   (Bonferroni, 14 patterns) au-dessus du hasard, ET les deux
                   moitiés de l'échantillon (in / out-of-sample) au-dessus,
                   ET gain moyen positif après coûts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app import indicators as ind

# Libellés bilingues et explication « en clair » de chaque pattern.
PATTERNS: dict[str, dict] = {
    "engulfing_bull": {"dir": 1, "group": "candle",
        "fr": "Avalement haussier", "en": "Bullish engulfing",
        "plain_fr": "Une bougie verte avale entièrement la bougie rouge précédente : les acheteurs reprennent la main.",
        "plain_en": "A green candle fully engulfs the prior red one: buyers take back control."},
    "engulfing_bear": {"dir": -1, "group": "candle",
        "fr": "Avalement baissier", "en": "Bearish engulfing",
        "plain_fr": "Une bougie rouge avale entièrement la bougie verte précédente : les vendeurs reprennent la main.",
        "plain_en": "A red candle fully engulfs the prior green one: sellers take back control."},
    "hammer": {"dir": 1, "group": "candle",
        "fr": "Marteau (pin bar haussière)", "en": "Hammer (bullish pin bar)",
        "plain_fr": "Longue mèche basse sur un plus bas local : le marché a rejeté les prix bas.",
        "plain_en": "Long lower wick at a local low: the market rejected lower prices."},
    "shooting_star": {"dir": -1, "group": "candle",
        "fr": "Étoile filante (pin bar baissière)", "en": "Shooting star (bearish pin bar)",
        "plain_fr": "Longue mèche haute sur un plus haut local : le marché a rejeté les prix hauts.",
        "plain_en": "Long upper wick at a local high: the market rejected higher prices."},
    "fvg_bull": {"dir": 1, "group": "fvg",
        "fr": "Gap de valeur haussier (FVG)", "en": "Bullish fair value gap",
        "plain_fr": "Montée si rapide qu'un trou de prix reste entre la bougie 1 et la bougie 3. Le prix revient souvent le combler.",
        "plain_en": "A move so fast that a price gap remains between candles 1 and 3. Price often comes back to fill it."},
    "fvg_bear": {"dir": -1, "group": "fvg",
        "fr": "Gap de valeur baissier (FVG)", "en": "Bearish fair value gap",
        "plain_fr": "Baisse si rapide qu'un trou de prix reste entre la bougie 1 et la bougie 3.",
        "plain_en": "A drop so fast that a price gap remains between candles 1 and 3."},
    "sweep_bull": {"dir": 1, "group": "sweep",
        "fr": "Chasse aux stops sous un creux", "en": "Liquidity sweep below a low",
        "plain_fr": "Le prix passe sous un ancien creux (déclenchant les stops), puis clôture au-dessus : piège vendeur.",
        "plain_en": "Price dips below a prior low (triggering stops), then closes back above: a seller trap."},
    "sweep_bear": {"dir": -1, "group": "sweep",
        "fr": "Chasse aux stops sur un sommet", "en": "Liquidity sweep above a high",
        "plain_fr": "Le prix passe au-dessus d'un ancien sommet, puis clôture en dessous : piège acheteur.",
        "plain_en": "Price pokes above a prior high, then closes back below: a buyer trap."},
    "bos_bull": {"dir": 1, "group": "structure",
        "fr": "Cassure de structure haussière (BOS)", "en": "Bullish break of structure",
        "plain_fr": "Clôture au-dessus du dernier sommet dans une tendance haussière : la tendance continue.",
        "plain_en": "Close above the last high in an uptrend: the trend continues."},
    "bos_bear": {"dir": -1, "group": "structure",
        "fr": "Cassure de structure baissière (BOS)", "en": "Bearish break of structure",
        "plain_fr": "Clôture sous le dernier creux dans une tendance baissière : la tendance continue.",
        "plain_en": "Close below the last low in a downtrend: the trend continues."},
    "choch_bull": {"dir": 1, "group": "structure",
        "fr": "Changement de caractère haussier (CHoCH)", "en": "Bullish change of character",
        "plain_fr": "Dans une baisse, clôture au-dessus du dernier sommet : premier signe de retournement.",
        "plain_en": "In a downtrend, a close above the last high: first sign of a reversal."},
    "choch_bear": {"dir": -1, "group": "structure",
        "fr": "Changement de caractère baissier (CHoCH)", "en": "Bearish change of character",
        "plain_fr": "Dans une hausse, clôture sous le dernier creux : premier signe de retournement.",
        "plain_en": "In an uptrend, a close below the last low: first sign of a reversal."},
    "double_bottom": {"dir": 1, "group": "chart",
        "fr": "Double creux", "en": "Double bottom",
        "plain_fr": "Deux creux au même niveau, puis cassure du sommet intermédiaire : le support a tenu deux fois.",
        "plain_en": "Two lows at the same level, then a break of the middle high: support held twice."},
    "double_top": {"dir": -1, "group": "chart",
        "fr": "Double sommet", "en": "Double top",
        "plain_fr": "Deux sommets au même niveau, puis cassure du creux intermédiaire : la résistance a tenu deux fois.",
        "plain_en": "Two highs at the same level, then a break of the middle low: resistance held twice."},
}

# Coût aller-retour (spread + glissement), en fraction du prix. 1 point de
# base sur l'or à 3 500 $ = 0,35 $ : environ 3 ticks GC, réaliste en séance.
COST_FRAC = 1e-4
MIN_EVENTS = 30

# Correction de Bonferroni : on teste 14 patterns à la fois. Au seuil de
# 95 % chacun, le hasard seul en « valide » un environ une fois sur deux.
# On exige donc un seuil de 1 - 0,05/14 par pattern (z ~ 2,91).
FAMILY_Z = 2.91


# ==========================================================================
# Détection
# ==========================================================================
def detect(df: pd.DataFrame, structure: ind.Structure | None = None) -> dict:
    """
    Tous les patterns de `df`. Chaque événement porte `i` (barre de
    détection : celle où le pattern devient CONNU, pas celle où il commence).
    """
    if len(df) < 10:
        return {"events": [], "fvgs": []}
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    a = ind.atr(df).shift(1).bfill().to_numpy(float)   # ATR connu avant la barre
    n = len(df)
    ev: list[dict] = []

    def add(i: int, kind: str, **extra) -> None:
        ev.append({"i": i, "kind": kind, "dir": PATTERNS[kind]["dir"], **extra})

    # -- Bougies ----------------------------------------------------------
    for i in range(5, n):
        rng = h[i] - l[i]
        if rng < 0.5 * a[i]:
            continue                                   # bougie insignifiante
        body = abs(c[i] - o[i])
        upper = h[i] - max(o[i], c[i])
        lower = min(o[i], c[i]) - l[i]
        pbody = abs(c[i - 1] - o[i - 1])
        if (c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1]
                and o[i] <= c[i - 1] and body > pbody and body >= 0.3 * a[i]):
            add(i, "engulfing_bull")
        elif (c[i - 1] > o[i - 1] and c[i] < o[i] and c[i] <= o[i - 1]
                and o[i] >= c[i - 1] and body > pbody and body >= 0.3 * a[i]):
            add(i, "engulfing_bear")
        if (lower >= 2 * body and lower >= 0.6 * rng and upper <= 0.25 * rng
                and l[i] <= l[i - 5:i].min()):
            add(i, "hammer")
        elif (upper >= 2 * body and upper >= 0.6 * rng and lower <= 0.25 * rng
                and h[i] >= h[i - 5:i].max()):
            add(i, "shooting_star")

    # -- Fair value gaps --------------------------------------------------
    fvgs: list[dict] = []
    for i in range(2, n):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= 0.15 * a[i]:
            fvgs.append({"i": i, "dir": 1, "top": float(l[i]), "bottom": float(h[i - 2])})
            add(i, "fvg_bull", top=float(l[i]), bottom=float(h[i - 2]))
        elif h[i] < l[i - 2] and l[i - 2] - h[i] >= 0.15 * a[i]:
            fvgs.append({"i": i, "dir": -1, "top": float(l[i - 2]), "bottom": float(h[i])})
            add(i, "fvg_bear", top=float(l[i - 2]), bottom=float(h[i]))
    for g in fvgs:                                     # comblement complet
        g["filled_at"] = None
        for j in range(g["i"] + 1, n):
            if (g["dir"] == 1 and l[j] <= g["bottom"]) or (g["dir"] == -1 and h[j] >= g["top"]):
                g["filled_at"] = j
                break

    # -- Structure : pivots, BOS / CHoCH, sweeps, doubles -----------------
    st = structure or ind.market_structure(df)
    for e in st.events:
        side = "bull" if e["dir"] == 1 else "bear"
        add(e["i"], f"{e['kind'].lower()}_{side}", level=e["level"], from_i=e["from_i"])

    # Sweep : mèche au-delà d'un pivot connu et intact, clôture en deçà.
    by_known: dict[int, list[dict]] = {}
    for s in st.swings:
        by_known.setdefault(s["known_at"], []).append(s)
    live_hi: list[dict] = []
    live_lo: list[dict] = []
    for t in range(n):
        for s in by_known.get(t, []):
            (live_hi if s["kind"] == "H" else live_lo).append(s)
        for s in list(live_hi):
            if h[t] > s["price"]:
                if c[t] < s["price"]:
                    add(t, "sweep_bear", level=s["price"], from_i=s["i"])
                live_hi.remove(s)                      # consommé, pris ou cassé
        for s in list(live_lo):
            if l[t] < s["price"]:
                if c[t] > s["price"]:
                    add(t, "sweep_bull", level=s["price"], from_i=s["i"])
                live_lo.remove(s)
        live_hi = live_hi[-6:]
        live_lo = live_lo[-6:]

    # Double sommet / creux : H - L - H (ou L - H - L) consécutifs.
    sw = st.swings
    for k in range(2, len(sw)):
        s1, mid, s2 = sw[k - 2], sw[k - 1], sw[k]
        if not (s1["kind"] == s2["kind"] != mid["kind"]):
            continue
        tol = 0.3 * a[s2["i"]]
        depth = abs(s2["price"] - mid["price"])
        if abs(s2["price"] - s1["price"]) > tol or depth < 1.0 * a[s2["i"]]:
            continue
        if s2["i"] - s1["i"] < 6:
            continue
        top = s1["kind"] == "H"
        for t in range(s2["known_at"], min(n, s2["known_at"] + 30)):
            if top and h[t] > max(s1["price"], s2["price"]) + tol:
                break                                  # invalidé avant confirmation
            if not top and l[t] < min(s1["price"], s2["price"]) - tol:
                break
            if (top and c[t] < mid["price"]) or (not top and c[t] > mid["price"]):
                add(t, "double_top" if top else "double_bottom",
                    p1=s1["i"], p2=s2["i"], neckline=mid["price"],
                    level=(s1["price"] + s2["price"]) / 2)
                break

    ev.sort(key=lambda e: e["i"])
    return {"events": ev, "fvgs": fvgs}


# ==========================================================================
# Mesure contre le hasard
# ==========================================================================
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def stats(df: pd.DataFrame, events: list[dict], horizon: int) -> list[dict]:
    """
    Pour chaque type : entrée à la clôture de la barre de détection, sortie
    `horizon` barres plus tard, coûts déduits. Les événements qui se
    chevauchent sont espacés (un seul par fenêtre de `horizon` barres) :
    100 barres d'affilée ne font pas 100 observations indépendantes.
    """
    c = df["close"].to_numpy(float)
    a = ind.atr(df).to_numpy(float)
    n = len(c)
    if n <= horizon + 20:
        return []
    fwd = c[horizon:] - c[:-horizon]
    cost = COST_FRAC * c[:-horizon]
    base = {1: float(np.mean(fwd - cost > 0)), -1: float(np.mean(-fwd - cost > 0))}

    out = []
    for kind, meta in PATTERNS.items():
        d = meta["dir"]
        idx, last = [], -10**9
        for e in events:
            if e["kind"] == kind and e["i"] + horizon < n and e["i"] >= last + horizon:
                idx.append(e["i"])
                last = e["i"]
        k = len(idx)
        if k == 0:
            out.append({"kind": kind, "n": 0, "label": "INSUFFICIENT",
                        "baseline": round(base[d], 3)})
            continue
        ii = np.array(idx)
        gain = d * (c[ii + horizon] - c[ii]) - COST_FRAC * c[ii]
        hits = gain > 0
        lo, hi = wilson(int(hits.sum()), k)                 # IC 95 % affiché
        lo_strict, _ = wilson(int(hits.sum()), k, FAMILY_Z)  # seuil de décision
        rate = float(hits.mean())
        half = k // 2
        r_is = float(hits[:half].mean()) if half else None
        r_oos = float(hits[half:].mean()) if k - half else None
        avg_atr = float(np.mean(gain / np.where(a[ii] > 0, a[ii], np.nan)))
        if k < MIN_EVENTS:
            label = "INSUFFICIENT"
        elif (lo_strict > base[d] and r_is is not None and r_oos is not None
              and r_is > base[d] and r_oos > base[d] and avg_atr > 0):
            label = "PLAUSIBLE"
        else:
            label = "NOT_PROVEN"
        out.append({
            "kind": kind, "n": k, "hit_rate": round(rate, 3),
            "ci": [round(lo, 3), round(hi, 3)], "baseline": round(base[d], 3),
            "lift": round(rate - base[d], 3),
            "hit_is": None if r_is is None else round(r_is, 3),
            "hit_oos": None if r_oos is None else round(r_oos, 3),
            "avg_gain_atr": round(avg_atr, 3) if not math.isnan(avg_atr) else None,
            "label": label,
        })
    return out
