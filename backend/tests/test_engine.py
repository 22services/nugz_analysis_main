"""
Tests de la couche de calcul, sur barres synthétiques (aucun appel réseau).

Lancer :  DISABLE_SCHEDULER=1 python -m pytest -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import indicators as ind
from app import patterns
from app.journal import _one_at_a_time, _score


def frame(closes, spread=1.0, volume=100.0, start="2026-01-05 00:00", freq="15min"):
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range(start, periods=len(c), freq=freq, tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread,
                         "low": np.minimum(o, c) - spread, "close": c,
                         "volume": volume}, index=idx)


# -- ATR ---------------------------------------------------------------------
def test_atr_constant_range():
    df = frame([100.0] * 50, spread=2.0)
    assert ind.atr(df).iloc[-1] == pytest.approx(4.0, rel=1e-6)


# -- VWAP --------------------------------------------------------------------
def test_vwap_weights_by_volume_and_resets_each_session():
    df = frame([10, 20, 30, 40], spread=0.0, freq="12h")
    df["high"] = df["low"] = df["close"]          # prix typique = clôture
    df["volume"] = [1, 3, 1, 1]
    labels = ind.session_labels(df.index, "UTC", 0)
    vw = ind.session_vwap(df, labels)
    # Séance 1 : (10*1 + 20*3) / 4 = 17.5 ; séance 2 repart de zéro.
    assert vw["vwap"].iloc[1] == pytest.approx(17.5)
    assert vw["vwap"].iloc[2] == pytest.approx(30.0)


def test_cme_session_starts_at_18h_new_york():
    idx = pd.DatetimeIndex(["2026-01-11 22:30", "2026-01-11 23:30"], tz="UTC")  # 17:30 / 18:30 NY
    labels = ind.session_labels(idx, "America/New_York", 18)
    assert str(labels.iloc[0]) == "2026-01-11" and str(labels.iloc[1]) == "2026-01-12"


# -- Profil de volume --------------------------------------------------------
def test_volume_profile_poc_and_value_area():
    df = frame([100.0] * 30 + [110.0] * 3, spread=0.5)
    p = ind.volume_profile(df, bin_size=0.5)
    assert p is not None
    assert abs(p.poc - 100.0) <= 0.5
    assert p.val <= 100.0 <= p.vah
    assert p.volume.sum() == pytest.approx(df["volume"].sum())


def test_volume_profile_none_without_volume():
    assert ind.volume_profile(frame([1, 2, 3], volume=0.0)) is None


# -- Structure ---------------------------------------------------------------
def zigzag(up=True, legs=8, n=6, step=2.0, pull=0.5):
    out, p = [], 100.0
    for k in range(legs):
        direction = 1 if (k % 2 == 0) == up else -1
        size = step if k % 2 == 0 else step * pull
        for _ in range(n):
            p += direction * size
            out.append(p)
    return out


def test_uptrend_detected_with_bos():
    st = ind.market_structure(frame(zigzag(up=True), spread=0.2))
    assert st.trend == 1
    assert any(e["kind"] == "BOS" and e["dir"] == 1 for e in st.events)


def test_downtrend_detected():
    st = ind.market_structure(frame(zigzag(up=False), spread=0.2))
    assert st.trend == -1


def test_swings_are_known_only_after_right_bars():
    sw = ind.swings(frame(zigzag(), spread=0.2), 3, 3)
    assert sw and all(s["known_at"] == s["i"] + 3 for s in sw)


def test_structure_has_no_lookahead():
    """La structure à la barre t ne change pas quand on ajoute le futur."""
    df = frame(zigzag(legs=12), spread=0.2)
    cut = 40
    past = ind.market_structure(df.iloc[:cut])
    full = ind.market_structure(df)
    assert [e for e in full.events if e["i"] < cut] == past.events


# -- Patterns ----------------------------------------------------------------
def test_bullish_fvg_detected():
    df = frame([100.0] * 20, spread=0.3)
    df.iloc[20 - 3, df.columns.get_loc("high")] = 100.3
    df.loc[df.index[-1], ["open", "low", "high", "close"]] = [103.0, 102.0, 104.0, 103.5]
    found = patterns.detect(df)
    assert any(e["kind"] == "fvg_bull" for e in found["events"])


def test_wilson_interval_contains_rate():
    lo, hi = patterns.wilson(55, 100)
    assert lo < 0.55 < hi and hi - lo < 0.25


@pytest.mark.parametrize("seed", range(8))
def test_random_walk_patterns_are_not_proven(seed):
    """Sur une marche aléatoire, aucun pattern ne doit sortir PLAUSIBLE."""
    rng = np.random.default_rng(seed)
    df = frame(1000 + np.cumsum(rng.normal(0, 1, 3000)), spread=0.6)
    st = patterns.stats(df, patterns.detect(df)["events"], horizon=4)
    assert st and all(s["label"] != "PLAUSIBLE" for s in st)


# -- Journal : notation d'un trade ------------------------------------------
def _entry(decision="LONG", stop=95.0, t1=110.0, chase=101.0):
    return {"decision": decision, "bar_end": "2026-01-05T00:15:00+00:00",
            "stop": stop, "t1": t1, "chase_limit": chase, "outcome": "OPEN"}


def test_win_when_target_hit_first():
    df = frame([100, 100, 105, 112], spread=0.5)
    e = _entry()
    assert _score(e, df) and e["outcome"] == "WIN" and e["pnl_r"] > 0


def test_same_bar_stop_and_target_counts_as_loss():
    df = frame([100, 100, 100], spread=0.5)
    df.iloc[2, df.columns.get_loc("high")] = 111
    df.iloc[2, df.columns.get_loc("low")] = 94
    e = _entry()
    assert _score(e, df) and e["outcome"] == "LOSS"


def test_missed_when_price_ran_past_chase_limit():
    df = frame([100, 104, 106], spread=0.5)
    e = _entry()
    assert _score(e, df) and e["outcome"] == "MISSED"


def test_one_position_at_a_time():
    base = {"decision": "SHORT", "outcome": "LOSS", "exit_at": "2026-01-05T02:00:00+00:00"}
    items = [{**base, "bar_end": f"2026-01-05T0{h}:00:00+00:00"} for h in (0, 1, 3)]
    assert len(_one_at_a_time(items)) == 2
