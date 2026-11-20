"""
Accès aux données de marché via OpenBB (Yahoo Finance, Réserve fédérale).

Gratuit et sans clé, mais avec trois pièges que ce module neutralise :

1. **Fuseaux.** OpenBB renvoie des horodatages *naïfs* dans le fuseau de la
   place de cotation (New York pour GC=F, UTC pour BTC-USD). On les remet en
   UTC explicite, sinon la VWAP de séance s'ancre à la mauvaise heure.

2. **Barre en formation.** Les données CME de Yahoo sont différées d'environ
   10 minutes, et la dernière barre renvoyée est souvent encore en train de
   se former. Une décision prise dessus serait du *look-ahead* déguisé : on
   ne garde que les barres closes, avec une marge (`DATA_DELAY_S`).

3. **Limitation de débit.** Tous les appels passent par un cache TTL en
   mémoire : plusieurs onglets ouverts ne doivent pas multiplier les appels.
"""
from __future__ import annotations

import math
import os
import threading
import time
import warnings
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from openbb import obb  # noqa: E402  (import lourd, après les filtres)

PROVIDER = "yfinance"

# Délai de diffusion des données gratuites + marge. Une barre n'est
# considérée close que si sa fin est antérieure à maintenant - DATA_DELAY_S.
DATA_DELAY_S = int(os.getenv("DATA_DELAY_S", "720"))

# intervalle -> (durée d'une barre, profondeur chargée en jours, TTL cache s)
# Yahoo limite l'intraday à 60 jours (5m/15m) et 730 jours (1h).
INTERVALS: dict[str, tuple[timedelta, int, int]] = {
    "5m": (timedelta(minutes=5), 20, 60),
    "15m": (timedelta(minutes=15), 59, 90),
    "1h": (timedelta(hours=1), 180, 300),
    "1d": (timedelta(days=1), 730, 900),
    "1W": (timedelta(weeks=1), 365 * 6, 3600),
}
INTRADAY = {"5m", "15m", "1h"}


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (now, value)
    return value


def clean(v: Any) -> Any:
    """NaN/inf -> None, dates -> ISO : le JSON doit rester strict."""
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def rows(result) -> list[dict[str, Any]]:
    return [{k: clean(v) for k, v in r.model_dump().items()} for r in result.results]


# --------------------------------------------------------------------------
# Fuseaux et séances
# --------------------------------------------------------------------------
_SUFFIX_TZ = {
    ".PA": "Europe/Paris", ".AS": "Europe/Amsterdam", ".DE": "Europe/Berlin",
    ".L": "Europe/London", ".SW": "Europe/Zurich", ".MI": "Europe/Rome",
    ".MC": "Europe/Madrid", ".T": "Asia/Tokyo", ".HK": "Asia/Hong_Kong",
    ".TO": "America/Toronto", ".AX": "Australia/Sydney",
}


def exchange_tz(symbol: str) -> str:
    """Fuseau de la place de cotation, selon les conventions de Yahoo."""
    s = symbol.upper()
    if s.endswith(("-USD", "-EUR", "-USDT")):
        return "UTC"                       # crypto : 24/7, horodatée en UTC
    if s.endswith("=X"):
        return "Europe/London"             # changes : Yahoo les date à Londres
    for suffix, tz in _SUFFIX_TZ.items():
        if s.endswith(suffix):
            return tz
    return "America/New_York"              # futures CME, indices US, actions US


def session_spec(symbol: str) -> tuple[str, int]:
    """
    (fuseau, heure de bascule) de la journée de trading.

    Les futures CME ouvrent la veille à 18 h (New York) : la séance du lundi
    commence le dimanche soir. Ancrer la VWAP à minuit couperait la séance
    asiatique en deux.
    """
    s = symbol.upper()
    if s.endswith("=F"):
        return "America/New_York", 18
    if s.endswith("=X"):
        return "America/New_York", 17      # le jour FX bascule à 17 h NY
    if s.endswith(("-USD", "-EUR", "-USDT")):
        return "UTC", 0
    return exchange_tz(symbol), 0


def is_cme_open(ts: datetime) -> bool:
    """Globex métaux : dimanche 18 h -> vendredi 17 h (NY), pause 17-18 h."""
    et = pd.Timestamp(ts).tz_convert("America/New_York")
    wd, h = et.weekday(), et.hour
    if wd == 5:                            # samedi
        return False
    if wd == 6:                            # dimanche : ouverture à 18 h
        return h >= 18
    if wd == 4 and h >= 17:                # vendredi après 17 h
        return False
    return h != 17                         # pause quotidienne


# --------------------------------------------------------------------------
# Barres
# --------------------------------------------------------------------------
def _fetch(symbol: str, interval: str, days: int) -> pd.DataFrame:
    start = (date.today() - timedelta(days=days)).isoformat()
    res = obb.equity.price.historical(
        symbol, provider=PROVIDER, interval=interval, start_date=start)
    data = rows(res)
    df = pd.DataFrame(
        [{"t": r["date"], "open": r.get("open"), "high": r.get("high"),
          "low": r.get("low"), "close": r.get("close"),
          "volume": r.get("volume") or 0.0} for r in data]
    )
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC"))
    df = df.dropna(subset=["open", "high", "low", "close"])
    idx = pd.to_datetime(df.pop("t"))
    if idx.dt.tz is None:
        tz = exchange_tz(symbol) if interval in INTRADAY else "UTC"
        idx = idx.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    df.index = pd.DatetimeIndex(idx).tz_convert("UTC")
    df = df[df.index.notna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.astype(float)


def bars(symbol: str, interval: str, days: int | None = None,
         complete_only: bool = True, now: datetime | None = None) -> pd.DataFrame:
    """
    Barres OHLCV indexées par leur DÉBUT, en UTC.

    `complete_only` retire les barres dont la fin n'est pas encore diffusée.
    """
    if interval not in INTERVALS:
        raise ValueError(f"interval must be one of {list(INTERVALS)}")
    step, default_days, ttl = INTERVALS[interval]
    days = days or default_days
    df = cached(f"bars:{symbol}:{interval}:{days}", ttl,
                lambda: _fetch(symbol, interval, days))
    if complete_only and interval in INTRADAY and len(df):
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now) - pd.Timedelta(seconds=DATA_DELAY_S) - step
        df = df[df.index <= cutoff]
    return df


def slice_asof(df: pd.DataFrame, asof: pd.Timestamp, step: timedelta) -> pd.DataFrame:
    """Barres entièrement closes à `asof` : la règle anti look-ahead."""
    return df[df.index + step <= asof]


def resample_4h(h1: pd.DataFrame) -> pd.DataFrame:
    """
    4 H reconstitué depuis le 1 H, aligné sur la séance CME (18 h NY) :
    barres 18-22, 22-02, 02-06, 06-10, 10-14, 14-18.
    """
    if h1.empty:
        return h1
    local = h1.tz_convert("America/New_York")
    agg = local.resample("4h", offset="2h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last",
         "volume": "sum"}).dropna(subset=["open"])
    return agg.tz_convert("UTC")
