"""
Graphique enrichi : bougies + VWAP et bandes + profil de volume + structure
+ patterns détectés, avec la statistique de chaque type de pattern.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app import data
from app import indicators as ind
from app import patterns

# Horizon de mesure des patterns (en barres) : ~1 h en intraday.
HORIZON = {"5m": 12, "15m": 4, "1h": 4, "1d": 5, "1W": 4}
SWING = {"5m": 3, "15m": 3, "1h": 3, "1d": 3, "1W": 2}


def _arr(s: pd.Series, d: int = 2) -> list:
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), d)
            for v in s.tolist()]


def build(symbol: str, interval: str, n_bars: int = 160) -> dict:
    df = data.bars(symbol, interval)                   # barres closes uniquement
    if len(df) < 40:
        raise ValueError("not enough data")
    k = SWING[interval]
    st = ind.market_structure(df, k, k)
    found = patterns.detect(df, st)
    stats = patterns.stats(df, found["events"], HORIZON[interval])
    a = ind.atr(df)

    start = max(0, len(df) - n_bars)
    view = df.iloc[start:]
    dec = 4 if float(df["close"].iloc[-1]) < 10 else 2
    out: dict = {
        "symbol": symbol, "interval": interval, "horizon": HORIZON[interval],
        "decimals": dec,
        "candles": [{"t": ts.isoformat(), "o": round(r.open, dec), "h": round(r.high, dec),
                     "l": round(r.low, dec), "c": round(r.close, dec), "v": float(r.volume)}
                    for ts, r in view.iterrows()],
        "atr": round(float(a.iloc[-1]), dec),
        "structure": {"trend": st.label},
        "has_volume": bool(view["volume"].sum() > 0),
    }

    # -- VWAP de séance (intraday uniquement) ------------------------------
    if interval in data.INTRADAY and out["has_volume"]:
        tz, roll = data.session_spec(symbol)
        labels = ind.session_labels(df.index, tz, roll)
        vw = ind.session_vwap(df, labels).iloc[start:]
        out["vwap"] = {k2: _arr(vw[k2], dec) for k2 in ("vwap", "u1", "l1", "u2", "l2")}
        # Ruptures de séance : on ne relie pas la VWAP d'un jour au suivant.
        lab = labels.iloc[start:].tolist()
        out["session_breaks"] = [i for i in range(1, len(lab)) if lab[i] != lab[i - 1]]
        sess_dates = sorted(set(labels))
        if len(sess_dates) >= 2:
            prev = df[labels == sess_dates[-2]]
            p = ind.volume_profile(prev, float(a.iloc[-1]) / 4)
            if p:
                out["prior_session"] = {"poc": round(p.poc, dec), "vah": round(p.vah, dec),
                                        "val": round(p.val, dec),
                                        "high": round(float(prev["high"].max()), dec),
                                        "low": round(float(prev["low"].min()), dec)}
    else:
        out["vwap"] = None

    # -- Profil du range visible -------------------------------------------
    vp = ind.volume_profile(view, float(a.iloc[-1]) / 3) if out["has_volume"] else None
    out["profile"] = vp.to_json(70) if vp else None

    # -- Structure et patterns dans la fenêtre -----------------------------
    rel = lambda i: i - start
    out["swings"] = [{**s, "i": rel(s["i"])} for s in st.swings
                     if s["i"] >= start and s["known_at"] < len(df)]
    out["events"] = [{**e, "i": rel(e["i"]),
                      **({"from_i": rel(e["from_i"])} if "from_i" in e else {}),
                      **({"p1": rel(e["p1"]), "p2": rel(e["p2"])} if "p1" in e else {})}
                     for e in found["events"] if e["i"] >= start]
    out["fvgs"] = [{**g, "i": rel(g["i"]),
                    "filled_at": None if g["filled_at"] is None else rel(g["filled_at"])}
                   for g in found["fvgs"] if g["i"] >= start]
    out["stats"] = stats
    out["meta"] = {k2: {kk: v for kk, v in m.items()} for k2, m in patterns.PATTERNS.items()}
    out["sample"] = {"bars": len(df), "from": df.index[0].isoformat(),
                     "to": (df.index[-1]).isoformat()}
    return out
