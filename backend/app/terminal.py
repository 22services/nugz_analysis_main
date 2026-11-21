"""
Terminal de marché façon Bloomberg - données réelles OpenBB.

Panneaux : GP (graphique), WEI (surveillance), DES (fiche), GC (courbe des
Treasuries), CN (actualités). Fournisseurs gratuits, sans clé (Yahoo
Finance, Réserve fédérale) ; données différées de 10 à 20 min.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from app import data
from app.data import PROVIDER, cached, obb, rows
from app.translate import translate_many

router = APIRouter(prefix="/api/terminal")

# L'or au centre, puis ce qui le fait bouger : dollar, taux, risque, énergie.
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


def _guard(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": PROVIDER, "engine": "openbb"}


@router.get("/watchlist")
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
                **w, "last": last, "change": chg,
                "change_pct": (chg / prev * 100) if chg is not None else None,
                "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
                "bid": q.get("bid"), "ask": q.get("ask"), "volume": q.get("volume"),
                "year_high": q.get("year_high"), "year_low": q.get("year_low"),
                "ma_50d": q.get("ma_50d"), "ma_200d": q.get("ma_200d"),
                "spark": closes[-22:],
            })
        return {"as_of": datetime.now(timezone.utc).isoformat(), "items": items}

    return _guard(lambda: cached("watchlist", 30, build))


@router.get("/history")
def history(symbol: str = Query("GC=F", max_length=20),
            interval: str = Query("1d")) -> dict:
    if interval not in data.INTERVALS:
        raise HTTPException(400, f"interval must be one of {list(data.INTERVALS)}")

    def build() -> dict:
        df = data.bars(symbol, interval, complete_only=False).tail(300)
        return {"symbol": symbol, "name": NAMES.get(symbol, symbol), "interval": interval,
                "candles": [{"t": ts.isoformat(), "o": r.open, "h": r.high, "l": r.low,
                             "c": r.close, "v": r.volume} for ts, r in df.iterrows()]}

    return _guard(build)


@router.get("/news")
def news(symbols: str = Query("GC=F,GLD", max_length=80),
         limit: int = Query(20, ge=1, le=50),
         lang: str = Query("en", pattern="^(en|fr)$")) -> dict:
    def build() -> dict:
        res = rows(obb.news.company(symbols, provider=PROVIDER, limit=limit))
        seen, items = set(), []
        for r in sorted(res, key=lambda r: r.get("date") or "", reverse=True):
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            items.append({"date": r.get("date"), "title": r.get("title"),
                          "url": r.get("url"), "source": r.get("source"),
                          "summary": (r.get("summary") or "")[:280]})
        items = items[:limit]
        if lang == "fr" and items:
            tr = translate_many([i["title"] or "" for i in items], "fr")
            for it, text, ok in zip(items, tr["texts"], tr["translated"]):
                it["title_original"] = it["title"]
                it["title"], it["translated"] = text, ok
        return {"items": items, "lang": lang}

    return _guard(lambda: cached(f"news:{symbols}:{limit}:{lang}", 300, build))


@router.get("/curve")
def curve() -> dict:
    """Courbe des Treasuries (Fed) : aujourd'hui contre il y a un mois."""
    tenors = ["month_1", "month_3", "month_6", "year_1", "year_2", "year_3",
              "year_5", "year_7", "year_10", "year_20", "year_30"]
    labels = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

    def build() -> dict:
        start = (date.today() - timedelta(days=45)).isoformat()
        res = rows(obb.fixedincome.government.treasury_rates(
            provider="federal_reserve", start_date=start))
        res = [r for r in res if r.get("year_10") is not None]
        if not res:
            raise RuntimeError("empty curve")
        latest, month_ago = res[-1], res[max(0, len(res) - 22)]
        pct = lambda r, k: round(r[k] * 100, 3) if r.get(k) is not None else None
        return {
            "as_of": latest["date"], "compare_to": month_ago["date"],
            "points": [{"tenor": lbl, "now": pct(latest, k), "prev": pct(month_ago, k)}
                       for k, lbl in zip(tenors, labels)],
        }

    return _guard(lambda: cached("curve", 3600, build))
