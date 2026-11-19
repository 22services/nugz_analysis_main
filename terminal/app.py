"""
Terminal de marche - service de donnees OpenBB.

Service separe de l'API du comite : OpenBB tire pandas 3 / FastAPI recent,
incompatibles avec les versions epinglees du backend. Il ne fait qu'une
chose : servir des donnees de marche reelles (fournisseurs gratuits, sans
cle) au panneau "Terminal" du dashboard.

Toutes les reponses passent par un cache TTL en memoire : plusieurs onglets
ouverts ne doivent pas multiplier les appels a Yahoo et nous faire limiter.
"""
from __future__ import annotations

import math
import threading
import time
import warnings
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

warnings.filterwarnings("ignore")
from openbb import obb  # noqa: E402  (import lourd, apres les filtres)

PROVIDER = "yfinance"

# Liste de surveillance facon terminal : l'or au centre, puis ce qui le
# fait bouger (dollar, taux reels, risque, energie).
WATCHLIST: list[dict[str, str]] = [
    {"symbol": "GC=F", "name": "Gold", "group": "metals"},
    {"symbol": "SI=F", "name": "Silver", "group": "metals"},
    {"symbol": "PL=F", "name": "Platinum", "group": "metals"},
    {"symbol": "HG=F", "name": "Copper", "group": "metals"},
    {"symbol": "DX-Y.NYB", "name": "Dollar Index", "group": "fx"},
    {"symbol": "EURUSD=X", "name": "EUR/USD", "group": "fx"},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "group": "fx"},
    {"symbol": "^TNX", "name": "US 10Y", "group": "rates"},
    {"symbol": "^FVX", "name": "US 5Y", "group": "rates"},
    {"symbol": "^GSPC", "name": "S&P 500", "group": "equity"},
    {"symbol": "^NDX", "name": "Nasdaq 100", "group": "equity"},
    {"symbol": "^VIX", "name": "VIX", "group": "equity"},
    {"symbol": "CL=F", "name": "WTI Crude", "group": "energy"},
    {"symbol": "BTC-USD", "name": "Bitcoin", "group": "crypto"},
]
NAMES = {w["symbol"]: w["name"] for w in WATCHLIST}

INTERVALS = {          # intervalle -> (profondeur en jours, TTL cache)
    "5m": (5, 60),
    "15m": (10, 120),
    "1h": (45, 300),
    "1d": (365, 900),
    "1W": (365 * 5, 3600),
}

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
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def rows(result) -> list[dict[str, Any]]:
    return [{k: clean(v) for k, v in r.model_dump().items()} for r in result.results]


# --------------------------------------------------------------------------
app = FastAPI(title="Terminal OpenBB", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])


@app.get("/api/terminal/health")
def health() -> dict:
    return {"status": "ok", "provider": PROVIDER, "engine": "openbb"}


@app.get("/api/terminal/watchlist")
def watchlist() -> dict:
    """Dernier prix, variation, sparkline 1 mois et fourchette 52 semaines."""
    def build() -> dict:
        symbols = ",".join(NAMES)
        start = (date.today() - timedelta(days=40)).isoformat()
        hist = rows(obb.equity.price.historical(
            symbols, provider=PROVIDER, interval="1d", start_date=start))
        series: dict[str, list[float]] = {}
        for r in hist:
            if r.get("close") is not None:
                series.setdefault(r.get("symbol") or symbols, []).append(r["close"])

        try:
            quotes = {q["symbol"]: q for q in rows(
                obb.equity.price.quote(symbols, provider=PROVIDER))}
        except Exception:
            quotes = {}

        items = []
        for w in WATCHLIST:
            s = w["symbol"]
            closes = series.get(s, [])
            q = quotes.get(s, {})
            last = closes[-1] if closes else None
            prev = closes[-2] if len(closes) > 1 else q.get("prev_close")
            chg = (last - prev) if last is not None and prev else None
            items.append({
                **w,
                "last": last,
                "change": chg,
                "change_pct": (chg / prev * 100) if chg is not None else None,
                "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
                "bid": q.get("bid"), "ask": q.get("ask"),
                "volume": q.get("volume"),
                "year_high": q.get("year_high"), "year_low": q.get("year_low"),
                "ma_50d": q.get("ma_50d"), "ma_200d": q.get("ma_200d"),
                "spark": closes[-22:],
            })
        return {"as_of": datetime.now(timezone.utc).isoformat(), "items": items}

    try:
        return cached("watchlist", 30, build)
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e


@app.get("/api/terminal/history")
def history(symbol: str = Query("GC=F", max_length=20),
            interval: str = Query("1d")) -> dict:
    if interval not in INTERVALS:
        raise HTTPException(400, f"interval must be one of {list(INTERVALS)}")
    days, ttl = INTERVALS[interval]
    yf_interval = {"1W": "1W"}.get(interval, interval)

    def build() -> dict:
        start = (date.today() - timedelta(days=days)).isoformat()
        data = rows(obb.equity.price.historical(
            symbol, provider=PROVIDER, interval=yf_interval, start_date=start))
        candles = [
            {"t": r["date"], "o": r["open"], "h": r["high"], "l": r["low"],
             "c": r["close"], "v": r.get("volume") or 0}
            for r in data if None not in (r.get("open"), r.get("close"))
        ]
        return {"symbol": symbol, "name": NAMES.get(symbol, symbol),
                "interval": interval, "candles": candles[-300:]}

    try:
        return cached(f"hist:{symbol}:{interval}", ttl, build)
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e


@app.get("/api/terminal/news")
def news(symbols: str = Query("GC=F,GLD", max_length=80),
         limit: int = Query(20, ge=1, le=50)) -> dict:
    def build() -> dict:
        data = rows(obb.news.company(symbols, provider=PROVIDER, limit=limit))
        seen, items = set(), []
        for r in sorted(data, key=lambda r: r.get("date") or "", reverse=True):
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            items.append({"date": r.get("date"), "title": r.get("title"),
                          "url": r.get("url"), "source": r.get("source"),
                          "summary": (r.get("summary") or "")[:280]})
        return {"items": items[:limit]}

    try:
        return cached(f"news:{symbols}:{limit}", 300, build)
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e


@app.get("/api/terminal/curve")
def curve() -> dict:
    """Courbe des Treasuries (Fed) : aujourd'hui contre il y a un mois."""
    tenors = ["month_1", "month_3", "month_6", "year_1", "year_2", "year_3",
              "year_5", "year_7", "year_10", "year_20", "year_30"]
    labels = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

    def build() -> dict:
        start = (date.today() - timedelta(days=45)).isoformat()
        data = rows(obb.fixedincome.government.treasury_rates(
            provider="federal_reserve", start_date=start))
        data = [r for r in data if r.get("year_10") is not None]
        if not data:
            raise RuntimeError("empty curve")
        latest, month_ago = data[-1], data[max(0, len(data) - 22)]
        pct = lambda r, k: round(r[k] * 100, 3) if r.get(k) is not None else None
        return {
            "as_of": latest["date"], "compare_to": month_ago["date"],
            "points": [{"tenor": lbl, "now": pct(latest, k), "prev": pct(month_ago, k)}
                       for k, lbl in zip(tenors, labels)],
        }

    try:
        return cached("curve", 3600, build)
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e
