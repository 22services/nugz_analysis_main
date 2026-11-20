"""
Cadence : une décision par barre de 15 minutes close.

Les données gratuites étant différées (~10 min sur le COMEX via Yahoo), la
barre 12:00-12:15 n'est complète qu'à ~12:25. Le comité se réunit donc à
chaque quart d'heure + DATA_DELAY_S + 30 s, sur la dernière barre close.
Une même barre n'est jamais décidée deux fois (clé = début de barre), ce qui
rend le week-end et la pause CME de 17 h inoffensifs : pas de nouvelle barre,
pas de nouvelle décision.

Au démarrage, le moteur est aussi REJOUÉ barre par barre sur les derniers
jours (source `replay`). Mêmes règles, mêmes seuils, aucune donnée future :
c'est la mesure honnête de ce que le comité aurait fait.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from app import committee, data
from app.journal import JOURNAL

log = logging.getLogger("scheduler")
REPLAY_DAYS = int(os.getenv("REPLAY_DAYS", "10"))
LAG_S = data.DATA_DELAY_S + 30

state = {"next_run_at": None, "last_run_at": None, "last_error": None,
         "replay": {"status": "pending", "done": 0, "total": 0}}


def next_run(now: datetime) -> datetime:
    """Prochain quart d'heure + délai de diffusion."""
    base = now - timedelta(seconds=LAG_S)
    q = base.replace(second=0, microsecond=0, minute=(base.minute // 15) * 15)
    return q + timedelta(minutes=15) + timedelta(seconds=LAG_S)


def tick() -> dict | None:
    """Une réunion du comité, sur la dernière barre close."""
    now = datetime.now(timezone.utc)
    frames = committee.load_frames()
    snap = committee.snapshot(frames, now)
    JOURNAL.evaluate(data.slice_asof(frames["m15"], pd.Timestamp(now)
                                     - pd.Timedelta(seconds=data.DATA_DELAY_S), committee.STEP))
    if snap.m15.empty:
        return None
    bar = snap.m15.index[-1].isoformat()
    if JOURNAL.has("live", bar) and JOURNAL.latest and JOURNAL.latest["bar_start"] == bar:
        return JOURNAL.latest
    d = committee.decide(snap)
    JOURNAL.record(d, "live")
    state["last_run_at"] = now.isoformat()
    return d


def replay(days: int = REPLAY_DAYS) -> None:
    """Rejoue le comité sur chaque barre des `days` derniers jours."""
    frames = committee.load_frames()
    m15 = frames["m15"]
    start = m15.index[-1] - pd.Timedelta(days=days)
    bars = m15.index[(m15.index >= start)]
    todo = [b for b in bars if not JOURNAL.has("replay", b.isoformat())]
    state["replay"] = {"status": "running", "done": 0, "total": len(todo)}
    for k, b in enumerate(todo):
        # La décision sur la barre b est prise quand b est close et diffusée.
        asof = b + committee.STEP + pd.Timedelta(seconds=LAG_S)
        try:
            snap = committee.snapshot(frames, asof)
            if snap.m15.empty or snap.m15.index[-1] != b:
                continue
            JOURNAL.record(committee.decide(snap), "replay", persist=False)
        except Exception as e:                         # une barre ratée n'arrête pas le rejeu
            log.warning("replay %s: %s", b, e)
        state["replay"]["done"] = k + 1
    JOURNAL.flush()
    JOURNAL.evaluate(m15)
    state["replay"]["status"] = "done"


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(tick)
            state["last_error"] = None
        except Exception as e:
            state["last_error"] = f"{type(e).__name__}: {e}"
            log.exception("tick failed")
        nxt = next_run(datetime.now(timezone.utc))
        state["next_run_at"] = nxt.isoformat()
        await asyncio.sleep(max(5.0, (nxt - datetime.now(timezone.utc)).total_seconds()))


async def start_replay() -> None:
    try:
        await asyncio.to_thread(replay)
    except Exception as e:
        state["replay"]["status"] = f"failed: {type(e).__name__}"
        log.exception("replay failed")
