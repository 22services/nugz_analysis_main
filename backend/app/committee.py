"""
Le comité : une décision par barre de 15 minutes close.

Pipeline (100 % déterministe, aucun LLM - un LLM qui calcule un ATR
hallucine, et un LLM qui dimensionne une position est un accident qui
attend son heure) :

    Données OpenBB (barres closes uniquement, figées à T)
        │
        ├── Structure      ─┐ groupe TENDANCE   (corrélés : comptent pour un)
        ├── VWAP           ─┘
        ├── Profil volume  ── groupe LOCALISATION
        ├── Cross-asset    ── groupe CONTEXTE (dollar, taux, VIX via OpenBB)
        └── Volatilité ATR ── FILTRE (ne vote pas, module la taille et le stop)
        ▼
    CIO : score pondéré par groupe, disjoncteur si tendance et localisation
          se contredisent
        ▼
    Red Team : « suppose que ce trade perd : pourquoi ? »
        ▼
    Risk Manager : stop, objectifs, ratio, taille - droit de veto
        ▼
    LONG / SHORT / PAS DE TRADE

Le vote naïf (« 3 haussiers contre 1 ») est affiché puis explicitement
écarté : structure et VWAP décrivent souvent le même phénomène.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app import data
from app import indicators as ind

ENGINE_VERSION = "2.0.0"
SYMBOL = os.getenv("DECISION_SYMBOL", "GC=F")
SYMBOL_NAME = os.getenv("DECISION_SYMBOL_NAME", "Gold futures (COMEX)")
CROSS = {"DX-Y.NYB": "Dollar Index", "^TNX": "US 10Y", "^VIX": "VIX"}

STEP = timedelta(minutes=15)

# --- Seuils : explicites et versionnés avec le moteur -------------------
DIRECTION_THRESHOLD = 25        # |score CIO| minimal pour proposer un trade
MIN_CONVICTION = 40             # en dessous : pas de trade
CONFLICT_LEVEL = 30             # disjoncteur tendance vs localisation
STALE_MINUTES = 45              # au-delà : données périmées -> veto
MAX_HOLD_BARS = 16              # stop temporel : 4 h
RISK_USD = float(os.getenv("RISK_PER_TRADE_USD", "500"))
POINT_VALUE = {"GC": 100.0, "MGC": 10.0}   # $ par point et par contrat

GROUP_WEIGHTS = {"trend": 0.45, "location": 0.35, "context": 0.20}

AGENTS = {
    "structure": {
        "name": {"fr": "Structure", "en": "Structure"},
        "role": {"fr": "Tendance 15m · 1H · 4H (sommets et creux)",
                 "en": "15m · 1H · 4H trend (highs and lows)"},
        "group": "trend"},
    "vwap": {
        "name": {"fr": "VWAP", "en": "VWAP"},
        "role": {"fr": "Prix moyen pondéré de la séance et ses bandes",
                 "en": "Session volume-weighted average price and bands"},
        "group": "trend"},
    "profile": {
        "name": {"fr": "Profil de volume", "en": "Volume profile"},
        "role": {"fr": "Où se sont échangés les volumes : POC, zone de valeur",
                 "en": "Where volume traded: POC, value area"},
        "group": "location"},
    "volatility": {
        "name": {"fr": "Volatilité (ATR)", "en": "Volatility (ATR)"},
        "role": {"fr": "Régime de volatilité, stop et taille",
                 "en": "Volatility regime, stop and size"},
        "group": "filter"},
    "cross": {
        "name": {"fr": "Cross-asset (OpenBB)", "en": "Cross-asset (OpenBB)"},
        "role": {"fr": "Dollar, taux US 10 ans, VIX en données réelles",
                 "en": "Dollar, US 10Y yield, VIX on live data"},
        "group": "context"},
}


def L(fr: str, en: str) -> dict:
    return {"fr": fr, "en": en}


def fmt(x: float | None, d: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:,.{d}f}".replace(",", " ")


def sgn(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ==========================================================================
# Instantané figé à T
# ==========================================================================
@dataclass
class Snapshot:
    symbol: str
    asof: pd.Timestamp
    m15: pd.DataFrame
    h1: pd.DataFrame
    h4: pd.DataFrame
    daily: pd.DataFrame
    cross: dict[str, pd.DataFrame]
    cross_error: str | None = None


def load_frames(symbol: str = SYMBOL) -> dict:
    """Historique complet (non tronqué) ; le découpage à T se fait ensuite."""
    frames = {
        "m15": data.bars(symbol, "15m", complete_only=False),
        "h1": data.bars(symbol, "1h", complete_only=False),
        "daily": data.bars(symbol, "1d", complete_only=False),
        "cross": {}, "cross_error": None,
    }
    try:
        frames["cross"] = {s: data.bars(s, "15m", days=15, complete_only=False)
                           for s in CROSS}
    except Exception as e:                             # contexte : non bloquant
        frames["cross_error"] = type(e).__name__
    return frames


def snapshot(frames: dict, asof: datetime | None = None,
             symbol: str = SYMBOL) -> Snapshot:
    """
    Tout ce que le comité lira, figé à `asof`. Une barre n'est visible que
    si elle était close ET diffusée (délai Yahoo) à cet instant.
    """
    asof = pd.Timestamp(asof or datetime.now(timezone.utc))
    visible = asof - pd.Timedelta(seconds=data.DATA_DELAY_S)
    m15 = data.slice_asof(frames["m15"], visible, STEP)
    h1 = data.slice_asof(frames["h1"], visible, timedelta(hours=1))
    h4 = data.resample_4h(h1.tail(1200))
    h4 = h4[h4.index + pd.Timedelta(hours=4) <= visible]
    cross = {s: data.slice_asof(df, visible, STEP) for s, df in frames["cross"].items()}
    return Snapshot(symbol=symbol, asof=asof, m15=m15, h1=h1, h4=h4,
                    daily=frames["daily"], cross=cross,
                    cross_error=frames.get("cross_error"))


def trading_session(ts: pd.Timestamp) -> str:
    if not data.is_cme_open(ts):
        return "CLOSED"
    et = ts.tz_convert("America/New_York")
    h = et.hour
    if h >= 18 or h < 3:
        return "ASIA"
    if h < 8:
        return "LONDON"
    return "NY"


SESSION_LABEL = {
    "ASIA": L("Asie", "Asia"), "LONDON": L("Londres", "London"),
    "NY": L("New York", "New York"), "CLOSED": L("Marché fermé", "Market closed"),
}
STRUCT_LABEL = {
    "UPTREND": L("Haussière", "Uptrend"), "DOWNTREND": L("Baissière", "Downtrend"),
    "RANGE": L("Indéterminée", "Undetermined"),
}


# ==========================================================================
# Marché : tous les chiffres, calculés une fois
# ==========================================================================
def market_features(s: Snapshot) -> dict:
    m15 = s.m15.tail(700)
    if len(m15) < 120:
        raise ValueError("not enough 15m bars")
    a_series = ind.atr(m15)
    a = float(a_series.iloc[-1])
    tz, roll = data.session_spec(s.symbol)
    labels = ind.session_labels(m15.index, tz, roll)
    cur = labels.iloc[-1]
    sess_dates = sorted(set(labels))
    prev = sess_dates[-2] if len(sess_dates) > 1 else None
    sess = m15[labels == cur]
    prev_df = m15[labels == prev] if prev else m15.iloc[:0]
    vw = ind.session_vwap(m15, labels)

    bin_size = a / 4 if a > 0 else None
    P = ind.volume_profile(prev_df, bin_size)
    D = ind.volume_profile(sess, bin_size) if len(sess) >= 4 else None

    daily = s.daily[s.daily.index.date < cur].tail(60)
    d_atr = float(ind.atr(daily).iloc[-1]) if len(daily) >= 15 else None
    sess_range = float(sess["high"].max() - sess["low"].min()) if len(sess) else 0.0

    full_atr = ind.atr(s.m15.tail(4000))
    pct = ind.percentile_rank(full_atr)

    last = m15.iloc[-1]
    bar_start = m15.index[-1]
    return {
        "m15": m15, "labels": labels, "sess": sess, "prev": prev_df, "vw": vw,
        "P": P, "D": D, "atr": a, "atr_series": a_series, "atr_pct": pct,
        "regime": ind.vol_regime(pct), "daily_atr": d_atr,
        "range_consumed": sess_range / d_atr if d_atr else None,
        "price": float(last["close"]), "bar_start": bar_start,
        "bar_end": bar_start + STEP, "session_date": cur,
        "session": trading_session(bar_start + STEP - pd.Timedelta(seconds=1)),
        "pdh": float(prev_df["high"].max()) if len(prev_df) else None,
        "pdl": float(prev_df["low"].min()) if len(prev_df) else None,
        "vwap": float(vw["vwap"].iloc[-1]) if not np.isnan(vw["vwap"].iloc[-1]) else None,
        "vwap_sd": float(vw["sd"].iloc[-1]) if not np.isnan(vw["sd"].iloc[-1]) else None,
    }


# ==========================================================================
# Les cinq voix
# ==========================================================================
def agent_out(aid: str, score: float, headline: dict, evidence: list[dict],
              status: str = "OK", warnings: list[dict] | None = None,
              extra: dict | None = None) -> dict:
    meta = AGENTS[aid]
    score = int(round(clip(score, -100, 100)))
    direction = ("NEUTRAL" if meta["group"] == "filter" or status != "OK"
                 else "LONG" if score >= 20 else "SHORT" if score <= -20 else "NEUTRAL")
    return {"id": aid, **meta, "status": status, "score": score,
            "direction": direction, "headline": headline, "evidence": evidence,
            "warnings": warnings or [], **(extra or {})}


def ev(label: dict | str, value: str | dict, reading: dict | None = None,
       supports: int = 0) -> dict:
    if isinstance(label, str):
        label = L(label, label)
    return {"label": label, "value": value, "reading": reading, "supports": supports}


def agent_structure(s: Snapshot, f: dict) -> dict:
    specs = [("15m", f["m15"].tail(500), 3, 1), ("1H", s.h1.tail(400), 3, 2),
             ("4H", s.h4.tail(250), 2, 3)]
    reads, total, evidence = {}, 0.0, []
    for tf, df, k, w in specs:
        if len(df) < 2 * k + 5:
            reads[tf] = None
            continue
        st = ind.market_structure(df, k, k)
        last_ev = st.events[-1] if st.events else None
        ago = len(df) - 1 - last_ev["i"] if last_ev else None
        total += w * st.trend
        lab = STRUCT_LABEL[st.label]
        tail = [x["label"] for x in st.swings if x["known_at"] < len(df) and x["label"]][-2:]
        reads[tf] = {"trend": st.trend, "label": st.label,
                     "last_event": last_ev and {**last_ev, "bars_ago": ago},
                     "swings": tail, "last_high": st.last_high, "last_low": st.last_low}
        if last_ev:
            e_fr = f"{last_ev['kind']} {'haussier' if last_ev['dir'] > 0 else 'baissier'} il y a {ago} barre(s) à {fmt(last_ev['level'])}"
            e_en = f"{'Bullish' if last_ev['dir'] > 0 else 'Bearish'} {last_ev['kind']} {ago} bar(s) ago at {fmt(last_ev['level'])}"
        else:
            e_fr, e_en = "Aucune cassure récente", "No recent break"
        sw_txt = " / ".join(tail) or "—"
        evidence.append(ev(tf, L(f"{lab['fr']} · {sw_txt}", f"{lab['en']} · {sw_txt}"),
                           L(e_fr, e_en), st.trend))
    score = total / 6 * 100
    trends = [r["trend"] for r in reads.values() if r]
    if trends and all(t == 1 for t in trends):
        head = L("Les trois unités de temps sont haussières : tendance alignée.",
                 "All three timeframes are rising: aligned uptrend.")
    elif trends and all(t == -1 for t in trends):
        head = L("Les trois unités de temps sont baissières : tendance alignée.",
                 "All three timeframes are falling: aligned downtrend.")
    else:
        big = reads.get("4H") or reads.get("1H")
        small = reads.get("15m")
        if big and small and big["trend"] and small["trend"] == -big["trend"]:
            head = L("Le 15 minutes va contre la tendance de fond : correction ou début de retournement.",
                     "The 15-minute runs against the larger trend: pullback or early reversal.")
        else:
            head = L("Structure mixte : les unités de temps ne racontent pas la même histoire.",
                     "Mixed structure: timeframes are not telling the same story.")
    return agent_out("structure", score, head, evidence, extra={"reads": reads})


def agent_vwap(s: Snapshot, f: dict) -> dict:
    if f["vwap"] is None or not f["atr"]:
        return agent_out("vwap", 0, L("Pas de volume : VWAP indisponible.",
                                      "No volume: VWAP unavailable."), [], status="UNAVAILABLE")
    a, c, v, sd = f["atr"], f["price"], f["vwap"], f["vwap_sd"] or 0.0
    vw = f["vw"]["vwap"]
    sess = f["sess"]
    dist = (c - v) / a
    sigma = (c - v) / sd if sd > 0 else 0.0
    n_s = len(sess)
    slope = (vw.iloc[-1] - vw.iloc[-5]) / a if n_s >= 5 else 0.0
    closes = sess["close"].tail(4)
    vwap_tail = vw.tail(len(closes))
    side = sgn(c - v)
    accepted = n_s >= 4 and all(sgn(x - y) == side for x, y in zip(closes, vwap_tail))

    score = side * min(abs(dist), 1.5) / 1.5 * 50 + clip(slope / 0.5, -1, 1) * 30
    score += side * 20 if accepted else 0
    warnings = []
    if abs(sigma) >= 2:
        score *= 0.4
        warnings.append(L(f"Prix à {sigma:+.1f} σ de la VWAP : étiré, risque de retour vers la moyenne.",
                          f"Price at {sigma:+.1f} σ from VWAP: stretched, mean-reversion risk."))
    if n_s < 4:
        score *= 0.5
        warnings.append(L("Séance trop jeune : la VWAP n'est pas encore significative.",
                          "Session too young: VWAP is not meaningful yet."))
    above = c > v
    head = (L(f"Prix {'au-dessus' if above else 'en dessous'} de la VWAP ({dist:+.2f} ATR)"
              + (", accepté depuis 4 barres" if accepted else "")
              + (", VWAP en hausse." if slope > 0.1 else ", VWAP en baisse." if slope < -0.1 else ", VWAP plate."),
              f"Price {'above' if above else 'below'} VWAP ({dist:+.2f} ATR)"
              + (", accepted for 4 bars" if accepted else "")
              + (", VWAP rising." if slope > 0.1 else ", VWAP falling." if slope < -0.1 else ", VWAP flat.")))
    evidence = [
        ev("VWAP", fmt(v), L(f"Écart {c - v:+.2f} $ = {dist:+.2f} ATR", f"Gap {c - v:+.2f} $ = {dist:+.2f} ATR"), side),
        ev(L("Bandes", "Bands"), f"{sigma:+.2f} σ",
           L("Au-delà de ±2 σ, le prix est statistiquement étiré.",
             "Beyond ±2 σ, price is statistically stretched."), 0),
        ev(L("Pente (4 barres)", "Slope (4 bars)"), f"{slope:+.2f} ATR",
           L("La pente dit qui contrôle la séance.", "The slope tells who controls the session."), sgn(slope)),
    ]
    return agent_out("vwap", score, head, evidence, warnings=warnings,
                     extra={"sigma": round(sigma, 2), "dist_atr": round(dist, 2)})


def agent_profile(s: Snapshot, f: dict) -> dict:
    P, D, c, a = f["P"], f["D"], f["price"], f["atr"]
    if P is None:
        return agent_out("profile", 0, L("Profil de la séance précédente indisponible.",
                                         "Previous session profile unavailable."), [], status="UNAVAILABLE")
    closes = f["sess"]["close"].tail(2).tolist() or [c]
    score = 0.0
    if c > P.vah:
        if all(x > P.vah for x in closes) and len(closes) == 2:
            score, head = 55, L("Prix accepté au-dessus de la zone de valeur d'hier : le marché cherche plus haut.",
                                "Price accepted above yesterday's value area: the market is seeking higher.")
        else:
            score, head = 20, L("Prix teste le haut de la zone de valeur d'hier, sans acceptation encore.",
                                "Price is testing above yesterday's value area, not accepted yet.")
    elif c < P.val:
        if all(x < P.val for x in closes) and len(closes) == 2:
            score, head = -55, L("Prix accepté sous la zone de valeur d'hier : le marché cherche plus bas.",
                                 "Price accepted below yesterday's value area: the market is seeking lower.")
        else:
            score, head = -20, L("Prix teste sous la zone de valeur d'hier, sans acceptation encore.",
                                 "Price is testing below yesterday's value area, not accepted yet.")
    else:
        pos = (c - P.val) / (P.vah - P.val) if P.vah > P.val else 0.5
        if pos > 0.8:
            score, head = -25, L("Prix en haut de la zone de valeur : rotation probable vers le POC.",
                                 "Price at the top of value: rotation toward the POC is likely.")
        elif pos < 0.2:
            score, head = 25, L("Prix en bas de la zone de valeur : rotation probable vers le POC.",
                                "Price at the bottom of value: rotation toward the POC is likely.")
        else:
            score, head = 0, L("Prix au milieu de la zone de valeur : marché en équilibre, pas d'avantage de localisation.",
                               "Price mid value area: balanced market, no location edge.")
    if D is not None and a and abs(D.poc - P.poc) > 0.25 * a:
        score += 15 * sgn(D.poc - P.poc)
    evidence = [
        ev(L("POC d'hier", "Prior POC"), fmt(P.poc),
           L("Prix le plus échangé hier : aimant naturel.", "Most traded price yesterday: a natural magnet."), sgn(c - P.poc)),
        ev(L("Zone de valeur d'hier", "Prior value area"), f"{fmt(P.val)} – {fmt(P.vah)}",
           L("70 % du volume d'hier. Dedans = équilibre ; dehors et accepté = tendance.",
             "70% of yesterday's volume. Inside = balance; outside and accepted = trend."), 0),
    ]
    if D is not None:
        mig = D.poc - P.poc
        evidence.append(ev(L("POC du jour", "Developing POC"), fmt(D.poc),
                           L(f"Migration {mig:+.2f} $ vs hier", f"Migration {mig:+.2f} $ vs yesterday"), sgn(mig)))
    return agent_out("profile", score, head, evidence)


def agent_volatility(s: Snapshot, f: dict) -> dict:
    pct, regime, rc = f["atr_pct"], f["regime"], f["range_consumed"]
    mult = {"COMPRESSED": 0.9, "NORMAL": 1.0, "EXPANDING": 1.0, "EXTREME": 0.7}[regime]
    reg = {"COMPRESSED": L("comprimée", "compressed"), "NORMAL": L("normale", "normal"),
           "EXPANDING": L("en expansion", "expanding"), "EXTREME": L("extrême", "extreme")}[regime]
    warnings = []
    if rc is not None and rc >= 1.0:
        warnings.append(L(f"La séance a déjà parcouru {rc:.0%} de son ATR journalier : peu de carburant pour prolonger.",
                          f"The session has already covered {rc:.0%} of its daily ATR: little fuel left to extend."))
    head = L(f"Volatilité {reg['fr']} ({pct}e percentile)"
             + (f", {rc:.0%} de l'amplitude journalière déjà consommée." if rc is not None else "."),
             f"Volatility {reg['en']} ({pct}th percentile)"
             + (f", {rc:.0%} of the daily range already used." if rc is not None else "."))
    evidence = [
        ev("ATR 15m", f"{fmt(f['atr'])} $", L("Mouvement moyen d'une barre : sert d'unité au stop.",
                                              "Average bar move: the unit for stops."), 0),
        ev(L("Percentile", "Percentile"), f"{pct}",
           L("Rang de l'ATR actuel sur ~60 jours.", "Rank of current ATR over ~60 days."), 0),
        ev(L("ATR journalier", "Daily ATR"), f"{fmt(f['daily_atr'])} $",
           L(f"Consommé : {rc:.0%}" if rc is not None else "—", f"Used: {rc:.0%}" if rc is not None else "—"), 0),
    ]
    return agent_out("volatility", 0, head, evidence, warnings=warnings,
                     extra={"multiplier": mult, "regime": regime})


def _change_vs_prev_session(df: pd.DataFrame, session_start: pd.Timestamp) -> tuple[float | None, float | None]:
    if df.empty:
        return None, None
    before = df[df.index < session_start]
    if before.empty:
        return float(df["close"].iloc[-1]), None
    return float(df["close"].iloc[-1]), float(before["close"].iloc[-1])


def agent_cross(s: Snapshot, f: dict) -> dict:
    if s.cross_error or not s.cross or any(df.empty for df in s.cross.values()):
        return agent_out("cross", 0, L("Données cross-asset indisponibles : contexte ignoré.",
                                       "Cross-asset data unavailable: context ignored."), [], status="UNAVAILABLE")
    start = f["sess"].index[0] if len(f["sess"]) else f["bar_start"]
    dxy, dxy0 = _change_vs_prev_session(s.cross["DX-Y.NYB"], start)
    tnx, tnx0 = _change_vs_prev_session(s.cross["^TNX"], start)
    vix, vix0 = _change_vs_prev_session(s.cross["^VIX"], start)
    dxy_pct = (dxy / dxy0 - 1) * 100 if dxy0 else 0.0
    tnx_bp = (tnx - tnx0) * 100 if tnx0 else 0.0
    vix_pct = (vix / vix0 - 1) * 100 if vix0 else 0.0

    # La relation or / dollar tient-elle en ce moment ? Corrélation des
    # rendements 15m sur ~5 séances.
    g = f["m15"]["close"].tail(460).pct_change()
    d = s.cross["DX-Y.NYB"]["close"].pct_change()
    j = pd.concat([g, d], axis=1, join="inner").dropna()
    corr = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > 60 else None
    active = corr is not None and corr < -0.1

    s_dxy = -clip(dxy_pct / 0.25, -1, 1) * 50
    s_tnx = -clip(tnx_bp / 4, -1, 1) * 30
    s_vix = clip(vix_pct / 8, -1, 1) * 20
    score = s_dxy + s_tnx + s_vix
    warnings = []
    if not active:
        score *= 0.5
        warnings.append(L("La corrélation or / dollar est rompue en ce moment : le contexte pèse moitié moins.",
                          "The gold / dollar correlation is broken right now: context weighs half."))
    tilt = "favorable" if score > 10 else "défavorable" if score < -10 else "neutre"
    tilt_en = "supportive" if score > 10 else "headwind" if score < -10 else "neutral"
    head = L(f"Contexte {tilt} pour l'or : dollar {dxy_pct:+.2f} %, 10 ans {tnx_bp:+.1f} pb, VIX {vix_pct:+.1f} %.",
             f"Context {tilt_en} for gold: dollar {dxy_pct:+.2f}%, 10Y {tnx_bp:+.1f} bp, VIX {vix_pct:+.1f}%.")
    evidence = [
        ev("Dollar Index", f"{fmt(dxy, 3)} ({dxy_pct:+.2f} %)",
           L("Un dollar plus fort renchérit l'or pour le reste du monde.",
             "A stronger dollar makes gold dearer for the rest of the world."), sgn(-dxy_pct)),
        ev(L("Taux US 10 ans", "US 10Y yield"), f"{fmt(tnx, 3)} % ({tnx_bp:+.1f} pb)",
           L("L'or ne verse pas d'intérêt : des taux en hausse le pénalisent.",
             "Gold pays no interest: rising yields weigh on it."), sgn(-tnx_bp)),
        ev("VIX", f"{fmt(vix)} ({vix_pct:+.1f} %)",
           L("Peur en hausse = demande de valeur refuge (lien PLAUSIBLE, non garanti).",
             "Rising fear = safe-haven demand (PLAUSIBLE link, not guaranteed)."), sgn(vix_pct)),
        ev(L("Corrélation or/dollar", "Gold/dollar correlation"), fmt(corr) if corr is not None else "—",
           L("Normale : négative. Proche de 0 ou positive = relation suspendue.",
             "Normal: negative. Near 0 or positive = relationship suspended."), 0),
    ]
    return agent_out("cross", score, head, evidence, warnings=warnings,
                     extra={"correlation": None if corr is None else round(corr, 2),
                            "relationship_active": active})


# ==========================================================================
# Red Team, Risk Manager, CIO
# ==========================================================================
def red_team(direction: int, f: dict, agents: dict, levels_against: list[tuple[float, str]]) -> dict:
    """Suppose que le trade perd. Pourquoi ? Chaque objection a une gravité 1-5."""
    obj: list[dict] = []
    a, c = f["atr"], f["price"]

    def add(sev: int, fr: str, en: str, targets: list[str]) -> None:
        obj.append({"severity": sev, "claim": L(fr, en), "targets": targets})

    r4 = (agents["structure"].get("reads") or {}).get("4H")
    if r4 and r4["trend"] == -direction:
        add(4, "Le trade va contre la tendance 4 heures : on nage à contre-courant.",
            "The trade fights the 4-hour trend: swimming against the current.", ["structure"])
    if levels_against:
        p, name = levels_against[0]
        room = abs(p - c) / a if a else 99
        if room < 1.0:
            add(3, f"Obstacle à {room:.2f} ATR seulement ({name['fr']} {fmt(p)}) : peu de place pour gagner.",
                f"Obstacle only {room:.2f} ATR away ({name['en']} {fmt(p)}): little room to win.", ["profile"])
    sig = agents["vwap"].get("sigma")
    if sig is not None and sig * direction >= 2:
        add(3, f"Prix déjà à {sig:+.1f} σ de la VWAP dans le sens du trade : on achète l'excès.",
            f"Price already {sig:+.1f} σ from VWAP in the trade direction: buying the excess.", ["vwap"])
    rc = f["range_consumed"]
    if rc is not None and rc >= 1.3:
        add(3, f"{rc:.0%} de l'ATR journalier déjà parcouru : la séance a probablement fait son mouvement.",
            f"{rc:.0%} of daily ATR already covered: the session has probably made its move.", ["volatility"])
    elif rc is not None and rc >= 1.0:
        add(2, f"{rc:.0%} de l'ATR journalier déjà parcouru.", f"{rc:.0%} of daily ATR already covered.", ["volatility"])
    r15 = (agents["structure"].get("reads") or {}).get("15m")
    le = r15 and r15.get("last_event")
    if le and le["kind"] == "CHoCH" and le["dir"] == -direction and le["bars_ago"] <= 4:
        add(3, f"CHoCH contraire il y a {le['bars_ago']} barre(s) sur le 15 minutes.",
            f"Opposite CHoCH {le['bars_ago']} bar(s) ago on the 15-minute.", ["structure"])
    if f["session"] == "ASIA":
        add(2, "Séance asiatique : liquidité faible, cassures moins fiables.",
            "Asian session: thin liquidity, breakouts less reliable.", [])
    cross = agents["cross"]
    if cross["status"] == "OK" and cross["score"] * direction <= -20:
        add(2, "Le dollar et les taux vont contre le trade.", "Dollar and yields run against the trade.", ["cross"])
    if cross["status"] != "OK":
        add(1, "Contexte cross-asset absent : décision prise à moitié aveugle.",
            "Cross-asset context missing: half-blind decision.", ["cross"])
    s, v = agents["structure"]["score"], agents["vwap"]["score"]
    if sgn(s) == sgn(v) != 0:
        add(1, "Structure et VWAP sont d'accord, mais mesurent en partie la même chose : un seul signal, pas deux.",
            "Structure and VWAP agree, but partly measure the same thing: one signal, not two.", ["structure", "vwap"])
    obj.sort(key=lambda o: -o["severity"])
    penalty = min(40, sum(o["severity"] for o in obj if o["severity"] >= 2) * 4)
    return {"objections": obj, "penalty": penalty}


def candidate_levels(f: dict, agents: dict) -> list[tuple[float, dict]]:
    """
    Niveaux MAJEURS seulement : ceux où des volumes ou des ordres se sont
    réellement accumulés. Les bandes ±1σ et les pivots 15m sont du bruit à
    l'échelle d'un objectif.
    """
    out: list[tuple[float, dict]] = []
    P, D = f["P"], f["D"]
    if P:
        out += [(P.poc, L("POC d'hier", "prior POC")), (P.vah, L("VAH d'hier", "prior VAH")),
                (P.val, L("VAL d'hier", "prior VAL"))]
    if D:
        out.append((D.poc, L("POC du jour", "developing POC")))
    if f["pdh"] is not None:
        out += [(f["pdh"], L("plus haut d'hier", "prior high")), (f["pdl"], L("plus bas d'hier", "prior low"))]
    if f["vwap"] is not None:
        out.append((f["vwap"], L("VWAP", "VWAP")))
        if f["vwap_sd"]:
            out += [(f["vwap"] + 2 * f["vwap_sd"], L("VWAP +2σ", "VWAP +2σ")),
                    (f["vwap"] - 2 * f["vwap_sd"], L("VWAP −2σ", "VWAP −2σ"))]
    r = (agents["structure"].get("reads") or {}).get("1H")
    if r and r["last_high"]:
        out.append((r["last_high"]["price"], L("sommet 1H", "1H high")))
    if r and r["last_low"]:
        out.append((r["last_low"]["price"], L("creux 1H", "1H low")))
    return [(float(p), n) for p, n in out if p is not None and not math.isnan(p)]


def risk_manager(direction: int, f: dict, agents: dict, levels: list[tuple[float, dict]],
                 asof: pd.Timestamp, multiplier: float) -> dict:
    a, c = f["atr"], f["price"]
    checks: list[dict] = []

    def check(ok: bool, fr: str, en: str, hard: bool = False, detail: dict | None = None):
        checks.append({"name": L(fr, en), "passed": bool(ok), "hard": hard, "detail": detail})

    age_min = (asof - f["bar_end"]).total_seconds() / 60
    fresh = age_min <= STALE_MINUTES
    check(fresh, "Données fraîches", "Fresh data", hard=True,
          detail=L(f"Dernière barre close il y a {age_min:.0f} min", f"Last closed bar {age_min:.0f} min ago"))
    open_ = data.is_cme_open(asof)
    check(open_, "Marché ouvert", "Market open", hard=True)

    # Stop : derrière le dernier pivot 15m, borné entre 0,8 et 2,5 ATR.
    r15 = (agents["structure"].get("reads") or {}).get("15m") or {}
    piv = r15.get("last_low") if direction > 0 else r15.get("last_high")
    stop_dist = 1.5 * a
    stop_src = L("1,5 ATR (pas de pivot exploitable)", "1.5 ATR (no usable swing)")
    if piv and (c - piv["price"]) * direction > 0:
        d = abs(c - piv["price"]) + 0.2 * a
        if 0.8 * a <= d <= 2.5 * a:
            stop_dist, stop_src = d, L("derrière le dernier pivot 15m", "beyond the last 15m swing")
        elif d < 0.8 * a:
            stop_dist, stop_src = 0.8 * a, L("0,8 ATR minimum (pivot trop proche)", "0.8 ATR minimum (swing too close)")
    stop = c - direction * stop_dist

    ahead = sorted([(p, n) for p, n in levels if (p - c) * direction >= 0.5 * a],
                   key=lambda x: abs(x[0] - c))
    if ahead:
        t1, t1_name = ahead[0]
        nxt = [x for x in ahead[1:] if abs(x[0] - t1) >= 0.5 * a]
        t2, t2_name = nxt[0] if nxt else (c + direction * 3 * stop_dist, L("3 R", "3 R"))
    else:
        t1, t1_name = c + direction * 1.5 * stop_dist, L("1,5 R (aucun obstacle)", "1.5 R (open air)")
        t2, t2_name = c + direction * 3 * stop_dist, L("3 R", "3 R")
    rr1 = abs(t1 - c) / stop_dist
    rr2 = abs(t2 - c) / stop_dist
    check(rr1 >= 1.0, "Ratio gain/risque ≥ 1 sur l'objectif 1", "Reward/risk ≥ 1 to target 1", hard=True,
          detail=L(f"{rr1:.2f} R jusqu'à {t1_name['fr']}", f"{rr1:.2f} R to {t1_name['en']}"))
    check(rr1 >= 1.5, "Ratio confortable (≥ 1,5)", "Comfortable ratio (≥ 1.5)")
    check(f["regime"] != "EXTREME", "Volatilité non extrême", "Volatility not extreme")

    hard_fail = any(not x["passed"] and x["hard"] for x in checks)
    soft_fail = any(not x["passed"] and not x["hard"] for x in checks)
    verdict = "REJECT" if hard_fail else "REDUCE" if soft_fail else "APPROVED"
    size_factor = 0.0 if verdict == "REJECT" else (0.5 if verdict == "REDUCE" else 1.0) * multiplier
    per_c = {k: stop_dist * v for k, v in POINT_VALUE.items()}
    sizes = {k: int(math.floor(RISK_USD * size_factor / v)) if v else 0 for k, v in per_c.items()}
    return {
        "verdict": verdict, "checks": checks,
        "entry": round(c, 2), "stop": round(stop, 2), "stop_atr": round(stop_dist / a, 2),
        "stop_source": stop_src,
        "t1": round(t1, 2), "t1_name": t1_name, "t2": round(t2, 2), "t2_name": t2_name,
        "rr1": round(rr1, 2), "rr2": round(rr2, 2),
        "chase_limit": round(c + direction * 0.3 * a, 2),
        "risk_usd": RISK_USD, "size_factor": round(size_factor, 2),
        "contracts": sizes, "risk_per_contract": {k: round(v, 0) for k, v in per_c.items()},
    }


def decide(s: Snapshot) -> dict:
    f = market_features(s)
    agents = {
        "structure": agent_structure(s, f),
        "vwap": agent_vwap(s, f),
        "profile": agent_profile(s, f),
        "volatility": agent_volatility(s, f),
        "cross": agent_cross(s, f),
    }
    ag = lambda k: agents[k]["score"] if agents[k]["status"] == "OK" else None

    # -- CIO : groupes indépendants, pas de vote naïf ------------------------
    trend_parts = [x for x in (ag("structure"), ag("vwap")) if x is not None]
    trend = float(np.mean(trend_parts)) if trend_parts else None
    groups = {"trend": trend, "location": ag("profile"), "context": ag("cross")}
    avail = {k: v for k, v in groups.items() if v is not None}
    wsum = sum(GROUP_WEIGHTS[k] for k in avail)
    raw = sum(GROUP_WEIGHTS[k] * v for k, v in avail.items()) / wsum if wsum else 0.0

    votes = [a["direction"] for k, a in agents.items() if AGENTS[k]["group"] != "filter"]
    naive = {"long": votes.count("LONG"), "short": votes.count("SHORT"),
             "neutral": votes.count("NEUTRAL")}

    reason = None
    if trend is None:
        reason = "NO_TREND_DATA"
    elif (ag("structure") is not None and ag("vwap") is not None
          and abs(ag("structure")) >= CONFLICT_LEVEL and abs(ag("vwap")) >= CONFLICT_LEVEL
          and sgn(ag("structure")) != sgn(ag("vwap"))):
        reason = "TREND_CONFLICT"
    elif (groups["location"] is not None and abs(trend) >= CONFLICT_LEVEL
          and abs(groups["location"]) >= CONFLICT_LEVEL and sgn(trend) != sgn(groups["location"])):
        reason = "TREND_VS_LOCATION"
    elif abs(raw) < DIRECTION_THRESHOLD:
        reason = "WEAK_SIGNAL"
    direction = sgn(raw) if reason is None else 0
    probe = direction or sgn(raw) or 1               # pour montrer le risque même sans trade

    levels = candidate_levels(f, agents)
    against = sorted([(p, n) for p, n in levels if (p - f["price"]) * probe > 0.05 * f["atr"]],
                     key=lambda x: abs(x[0] - f["price"]))
    rt = red_team(probe, f, agents, against)
    mult = agents["volatility"]["multiplier"]
    risk = risk_manager(probe, f, agents, levels, s.asof, mult)

    conviction = 0
    if direction:
        conviction = int(round(clip(abs(raw) * 1.3 - rt["penalty"], 0, 100) * mult
                               - (10 if agents["cross"]["status"] != "OK" else 0)))
        conviction = max(0, conviction)
        if risk["verdict"] == "REJECT":
            reason, direction = "RISK_VETO", 0
        elif conviction < MIN_CONVICTION:
            reason, direction = "LOW_CONVICTION", 0

    decision = "LONG" if direction > 0 else "SHORT" if direction < 0 else "NO_TRADE"
    rationale = _rationale(decision, reason, raw, groups, rt, risk, f, agents)
    bar_end = f["bar_end"]
    return {
        "engine_version": ENGINE_VERSION,
        "symbol": s.symbol, "name": SYMBOL_NAME,
        "bar_start": f["bar_start"].isoformat(), "bar_end": bar_end.isoformat(),
        "decided_at": s.asof.isoformat(),
        "decision": decision, "reason": reason,
        "conviction": conviction if decision != "NO_TRADE" else 0,
        "rationale": rationale,
        "market": {
            "price": round(f["price"], 2), "session": f["session"],
            "session_label": SESSION_LABEL[f["session"]],
            "atr": round(f["atr"], 2), "atr_pct": f["atr_pct"], "regime": f["regime"],
            "daily_atr": None if f["daily_atr"] is None else round(f["daily_atr"], 2),
            "range_consumed": None if f["range_consumed"] is None else round(f["range_consumed"], 2),
            "vwap": None if f["vwap"] is None else round(f["vwap"], 2),
            "vwap_sd": None if f["vwap_sd"] is None else round(f["vwap_sd"], 2),
            "poc": f["P"] and round(f["P"].poc, 2), "vah": f["P"] and round(f["P"].vah, 2),
            "val": f["P"] and round(f["P"].val, 2), "dpoc": f["D"] and round(f["D"].poc, 2),
            "pdh": f["pdh"], "pdl": f["pdl"],
        },
        "agents": list(agents.values()),
        "cio": {"raw_score": round(raw, 1), "threshold": DIRECTION_THRESHOLD,
                "min_conviction": MIN_CONVICTION, "groups": {k: None if v is None else round(v, 1)
                                                             for k, v in groups.items()},
                "weights": GROUP_WEIGHTS, "naive_vote": naive, "probe_direction": probe},
        "red_team": rt,
        "risk": risk,
    }


REASONS = {
    "NO_TREND_DATA": L("Données de tendance indisponibles : le système refuse de décider à l'aveugle.",
                       "Trend data unavailable: the system refuses to decide blind."),
    "TREND_CONFLICT": L("Structure et VWAP se contredisent franchement : la tendance n'est pas lisible.",
                        "Structure and VWAP clearly disagree: the trend is unreadable."),
    "TREND_VS_LOCATION": L("La tendance pousse d'un côté, le profil de volume de l'autre : disjoncteur, on s'abstient.",
                           "Trend pushes one way, volume profile the other: circuit breaker, we stand aside."),
    "WEAK_SIGNAL": L("Aucun avantage net : les signaux s'annulent ou sont trop faibles.",
                     "No net edge: signals cancel out or are too weak."),
    "RISK_VETO": L("Le Risk Manager met son veto.", "The Risk Manager vetoes."),
    "LOW_CONVICTION": L("Signal présent, mais les objections le rendent trop fragile.",
                        "A signal exists, but the objections make it too fragile."),
}


def _rationale(decision: str, reason: str | None, raw: float, groups: dict,
               rt: dict, risk: dict, f: dict, agents: dict) -> dict:
    if decision == "NO_TRADE":
        base = REASONS.get(reason, L("Pas de trade.", "No trade."))
        if reason == "RISK_VETO":
            failed = [c["name"] for c in risk["checks"] if not c["passed"] and c["hard"]]
            if failed:
                base = L(base["fr"] + " Motif : " + ", ".join(x["fr"].lower() for x in failed) + " non respecté.",
                         base["en"] + " Reason: " + ", ".join(x["en"].lower() for x in failed) + " failed.")
        return base
    side_fr = "acheteur" if decision == "LONG" else "vendeur"
    side_en = "long" if decision == "LONG" else "short"
    strongest = max(((k, v) for k, v in groups.items() if v is not None), key=lambda kv: abs(kv[1]))
    gname = {"trend": L("la tendance", "the trend"), "location": L("la localisation dans le profil", "location in the profile"),
             "context": L("le contexte cross-asset", "cross-asset context")}[strongest[0]]
    top = rt["objections"][0] if rt["objections"] else None
    return L(
        f"Biais {side_fr} porté surtout par {gname['fr']} (score {raw:+.0f}). "
        f"Entrée vers {fmt(risk['entry'])}, stop {fmt(risk['stop'])}, objectif {fmt(risk['t1'])} ({risk['rr1']:.1f} R)."
        + (f" Principale objection : {top['claim']['fr'][0].lower() + top['claim']['fr'][1:]}" if top else ""),
        f"{side_en.capitalize()} bias driven mainly by {gname['en']} (score {raw:+.0f}). "
        f"Entry near {fmt(risk['entry'])}, stop {fmt(risk['stop'])}, target {fmt(risk['t1'])} ({risk['rr1']:.1f} R)."
        + (f" Main objection: {top['claim']['en'][0].lower() + top['claim']['en'][1:]}" if top else ""),
    )
