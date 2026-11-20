"""
API nugz - un seul service.

  /api/decision          décision du comité sur la dernière barre 15m close
  /api/decision/history  journal (live + rejeu) et statistiques
  /api/chart             graphique enrichi : VWAP, profil, structure, patterns
  /api/terminal/*        terminal OpenBB (surveillance, graphique, courbe, news)

Un seul worker uvicorn : le cache, le planificateur et le journal vivent en
mémoire du process (le journal est aussi persisté sur disque).
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import charts, committee, data, scheduler, terminal
from app.journal import JOURNAL


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    if os.getenv("DISABLE_SCHEDULER") != "1":
        tasks.append(asyncio.create_task(scheduler.run_forever()))
        tasks.append(asyncio.create_task(scheduler.start_replay()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="nugz - comité Or", version=committee.ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                   allow_headers=["*"])
app.include_router(terminal.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "engine_version": committee.ENGINE_VERSION,
            "symbol": committee.SYMBOL, "data_delay_s": data.DATA_DELAY_S,
            "schedule": scheduler.state}


@app.get("/api/decision")
def decision() -> dict:
    if not JOURNAL.latest:
        raise HTTPException(503, "warming up")
    return {**JOURNAL.latest, "schedule": {
        "next_run_at": scheduler.state["next_run_at"],
        "last_error": scheduler.state["last_error"],
        "data_delay_s": data.DATA_DELAY_S}}


@app.post("/api/decision/refresh")
async def refresh() -> dict:
    """Relance le comité maintenant (sans effet si la barre est déjà décidée)."""
    try:
        await asyncio.to_thread(scheduler.tick)
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e
    return decision()


@app.get("/api/decision/history")
def history(source: str = Query("live", pattern="^(live|replay)$"),
            limit: int = Query(96, ge=1, le=2000)) -> dict:
    return {"items": JOURNAL.history(source, limit),
            "stats": {"live": JOURNAL.stats("live"), "replay": JOURNAL.stats("replay")},
            "replay": scheduler.state["replay"]}


@app.get("/api/chart")
def chart(symbol: str = Query(committee.SYMBOL, max_length=20),
          interval: str = Query("15m"),
          bars: int = Query(160, ge=30, le=400)) -> dict:
    if interval not in data.INTERVALS:
        raise HTTPException(400, f"interval must be one of {list(data.INTERVALS)}")
    key = f"chart:{symbol}:{interval}:{bars}"
    try:
        return data.cached(key, 60, lambda: charts.build(symbol, interval, bars))
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"provider error: {type(e).__name__}") from e
