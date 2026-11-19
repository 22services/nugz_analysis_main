"""
Donnees simulees. V1 uniquement.

Chaque valeur produite ici porte `connected: False` et remonte jusqu'a l'UI
comme telle: il ne doit jamais y avoir d'ambiguite entre une donnee simulee et
une donnee de marche. Le jour ou Apify / le feed OHLCV sont branches, ce module
est remplace, pas contourne.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.schemas import (
    CalendarEvent,
    ContractContext,
    DataSource,
    Localized,
    SessionContext,
)

SEED = 20260921
BASE_PRICE = 2_412.40          # GC, ordre de grandeur realiste
TF_MINUTES = {"5m": 5, "15m": 15, "1H": 60, "4H": 240, "1D": 1440}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# OHLCV synthetique
# --------------------------------------------------------------------------
def generate_ohlcv(timeframe: str, bars: int = 400, seed: int = SEED) -> pd.DataFrame:
    """
    Marche simule par marche aleatoire a volatilite variable, plus une legere
    derive et quelques respirations de volatilite. Le but n'est pas le realisme
    statistique: c'est d'alimenter des indicateurs qui produisent une structure
    lisible dans le dashboard.
    """
    minutes = TF_MINUTES[timeframe]
    rng = np.random.default_rng(seed + minutes)

    # Volatilite par barre, calee sur ~0.6% par jour ramene au timeframe.
    daily_vol = 0.006
    vol = daily_vol * np.sqrt(minutes / 1440)

    # Regimes de volatilite alternes (compression -> expansion).
    regime = np.repeat(rng.uniform(0.6, 1.7, size=bars // 20 + 1), 20)[:bars]
    drift = np.linspace(0, 0.004, bars) * rng.choice([-1, 1])

    returns = rng.normal(drift / bars, vol * regime)
    close = BASE_PRICE * np.exp(np.cumsum(returns))

    spread = close * vol * regime
    high = close + np.abs(rng.normal(0, spread * 0.8))
    low = close - np.abs(rng.normal(0, spread * 0.8))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])

    # Le volume suit la volatilite: les grosses barres se traitent.
    volume = rng.lognormal(mean=7.5, sigma=0.45, size=bars) * regime

    end = _now().replace(second=0, microsecond=0)
    index = pd.date_range(end=end, periods=bars, freq=f"{minutes}min", tz="UTC")

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    ).round(2)


def build_market(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Les 5 unités de temps du PDF: 5m / 15m / 1H / 4H / Daily."""
    return {tf: generate_ohlcv(tf, seed=seed) for tf in TF_MINUTES}


# --------------------------------------------------------------------------
# Contexte contrat / session
# --------------------------------------------------------------------------
def contract_context(now: datetime | None = None) -> ContractContext:
    now = now or _now()
    expiry = (now + timedelta(days=38)).replace(hour=18, minute=30)
    roll = expiry - timedelta(days=5)
    days_to_roll = max((roll - now).days, 0)

    warning = None
    if days_to_roll <= 7:
        warning = Localized(
            fr=f"Roll du contrat dans {days_to_roll} jours : volume et open "
               "interest migrent vers l'échéance suivante, la structure "
               "peut se déformer.",
            en=f"Contract roll in {days_to_roll} days: volume and open interest are "
               "migrating to the next expiry, structure readings may distort.",
        )

    return ContractContext(
        symbol="GCZ5",
        is_front_month=True,
        expiry=expiry,
        roll_date=roll,
        days_to_roll=days_to_roll,
        series_type="front_month",
        roll_warning=warning,
    )


def session_context(now: datetime | None = None) -> SessionContext:
    """Approximation des sessions en UTC."""
    now = now or _now()
    h = now.hour
    if 23 <= h or h < 7:
        session, liquid, open_h = "ASIA", False, 23
    elif 7 <= h < 13:
        session, liquid, open_h = "LONDON", True, 7
    elif 13 <= h < 21:
        session, liquid, open_h = "NY", True, 13
    else:
        session, liquid, open_h = "CLOSED", False, 21

    since = (h - open_h) % 24 * 60 + now.minute
    return SessionContext(
        session=session,                 # type: ignore[arg-type]
        is_liquid_hours=liquid,
        minutes_since_open=since,
        minutes_to_close=max(0, 8 * 60 - since),
    )


# --------------------------------------------------------------------------
# Sources (toutes non connectees en V1)
# --------------------------------------------------------------------------
def data_sources(now: datetime | None = None) -> list[DataSource]:
    now = now or _now()
    spec = [
        ("OHLCV GC (front-month)", "price", 45, 300),
        ("XAU/USD spot", "price", 20, 180),
        ("DXY", "macro", 90, 600),
        ("UST 2Y / 10Y", "macro", 120, 900),
        ("Taux réels 10Y (TIPS)", "macro", 240, 3600),
        ("Open interest / volume CME", "futures", 600, 3600),
        ("Courbe GC / calendar spreads", "futures", 600, 3600),
        ("Calendrier macro", "calendar", 1800, 21600),
        ("COT (CFTC)", "positioning", 190_000, 864_000),
        ("Flux news", "news", 300, 1800),
    ]
    return [
        DataSource(
            name=name,
            kind=kind,                    # type: ignore[arg-type]
            last_update=now - timedelta(seconds=age),
            age_seconds=age,
            max_age_seconds=max_age,
            is_stale=age > max_age,
            connected=False,              # V1: rien n'est branche
        )
        for name, kind, age, max_age in spec
    ]


# --------------------------------------------------------------------------
# Calendrier macro
# --------------------------------------------------------------------------
def calendar(now: datetime | None = None) -> list[CalendarEvent]:
    now = now or _now()
    spec = [
        ("Core CPI (US)", "Inflation sous-jacente (US)", 186, "CRITICAL",
         [("DXY", "DXY"), ("Taux réels", "Real rates"), ("Or", "Gold")],
         "0,3 % m/m", "0,2 % m/m"),
        ("Fed speaker - Williams", "Discours Fed — Williams", 420, "MEDIUM",
         [("Anticipations Fed", "Fed expectations")], None, None),
        ("Initial Jobless Claims", "Inscriptions chômage hebdo", 1_320, "MEDIUM",
         [("Taux courts", "Short rates")], "221 k", "218 k"),
        ("FOMC decision", "Décision FOMC", 8_640, "CRITICAL",
         [("DXY", "DXY"), ("Taux réels", "Real rates"), ("Or", "Gold"),
          ("Actions", "Equities")], "Statu quo", "Statu quo"),
        ("Core PCE", "Core PCE", 15_800, "HIGH",
         [("Taux réels", "Real rates"), ("Or", "Gold")], "0,2 % m/m", "0,2 % m/m"),
    ]
    return [
        CalendarEvent(
            name=Localized(fr=fr, en=en),
            scheduled_at=now + timedelta(minutes=mins),
            minutes_until=mins,
            importance=imp,               # type: ignore[arg-type]
            exposed_variables=[Localized(fr=a, en=b) for a, b in vars_],
            consensus=cons,
            previous=prev,
        )
        for en, fr, mins, imp, vars_, cons, prev in spec
    ]


# --------------------------------------------------------------------------
# Macro simulee
# --------------------------------------------------------------------------
def macro_snapshot(seed: int = SEED) -> dict:
    """
    Instantane cross-asset. Le champ `relationship_active` est le plus
    important : il dit si la correlation historique tient dans le regime
    actuel. Une relation rompue doit retirer de la force au signal macro,
    pas etre appliquee mecaniquement.
    """
    rng = np.random.default_rng(seed + 7)

    spec = [
        ("DXY", 97.42, -0.31, -0.72, "DXY"),
        ("UST 10Y", 4.18, +0.04, -0.55, "UST 10Y"),
        ("Taux réel 10Y", 1.92, +0.03, -0.81, "Real 10Y"),
        ("S&P 500", 6_142.0, +0.42, +0.12, "S&P 500"),
        ("VIX", 14.8, -0.60, +0.28, "VIX"),
    ]

    cross = []
    for asset, value, change, normal, asset_en in spec:
        live = float(np.clip(normal + rng.normal(0, 0.28), -1, 1))
        active = abs(live - normal) < 0.35 and np.sign(live) == np.sign(normal)
        # Correlation negative: une hausse de l'actif pese sur l'or.
        if normal < 0:
            impact = "SHORT" if change > 0 else "LONG"
        else:
            impact = "LONG" if change > 0 else "SHORT"
        cross.append(
            {
                "asset": asset,
                "asset_en": asset_en,
                "value": f"{value:,.2f}",
                "change": f"{change:+.2f} %",
                "normal_correlation": round(normal, 2),
                "live_correlation": round(live, 2),
                "relationship_active": bool(active),
                "impact_on_gold": impact,
            }
        )

    return {
        "regime": "DISINFLATION",
        "cross_assets": cross,
        "fed_fr": "Le marché price une pause, avec une première baisse "
                  "anticipée au trimestre suivant. Les taux réels restent "
                  "le moteur dominant de l'or.",
        "fed_en": "The market prices a pause, with a first cut expected next "
                  "quarter. Real rates remain the dominant driver for gold.",
    }


# --------------------------------------------------------------------------
# Futures / positionnement simules
# --------------------------------------------------------------------------
def futures_snapshot(market: dict[str, pd.DataFrame], seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed + 11)
    df = market["5m"]

    recent = float(df["volume"].tail(12).mean())
    baseline = float(df["volume"].tail(120).mean()) or 1.0
    now = _now()
    cot_age_days = 4

    return {
        "volume": round(recent, 0),
        "volume_vs_avg": round(recent / baseline, 2),
        "open_interest": int(rng.integers(410_000, 470_000)),
        "oi_change": int(rng.integers(-9_000, 12_000)),
        "basis": round(float(rng.normal(2.4, 1.8)), 2),
        "curve_state": "CONTANGO",
        "calendar_spread": round(float(rng.normal(3.1, 0.6)), 2),
        "liquidity_score": int(rng.integers(62, 94)),
        "cot_net": int(rng.integers(150_000, 240_000)),
        "cot_as_of": now - timedelta(days=cot_age_days),
        "cot_age_days": cot_age_days,
    }
