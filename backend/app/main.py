"""
API du dashboard.

V1 : aucun outil externe n'est branche. Toutes les reponses portent
`connected: false` sur leurs sources, et l'UI l'affiche sans ambiguite. Le but
de cette etape est de valider la structure de decision avant de payer des
donnees de marche.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agents import registry
from app.journal import JOURNAL
from app.pipeline.orchestrator import Orchestrator, build_market_snapshot, manual_trigger
from app.schemas import FEATURE_SCHEMA_VERSION

# Scenarios de demonstration. Chaque graine produit un etat de marche qui mene
# a une decision differente - utile pour montrer que NO TRADE est une sortie
# normale du systeme et pas une panne.
SCENARIOS = {
    "long": {"seed": 1003, "fr": "Setup haussier validé", "en": "Validated bullish setup"},
    "short": {"seed": 1002, "fr": "Setup baissier validé", "en": "Validated bearish setup"},
    "reduced": {"seed": 1018, "fr": "Taille réduite par le risque", "en": "Size cut by risk"},
    "no_trade": {"seed": 1000, "fr": "Veto du Risk Manager", "en": "Risk Manager veto"},
    "conflict": {"seed": 1024, "fr": "Analystes en désaccord", "en": "Analysts disagree"},
}

_subscribers: set[asyncio.Queue] = set()


async def _broadcast(run) -> None:
    payload = json.dumps({
        "run_id": run.run_id,
        "stage": run.stage.value,
        "decision": run.decision.value if run.decision else None,
        "conviction": run.conviction,
        "agents": {
            aid: o.status.value for aid, o in run.outputs.items()
        },
    })
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Un premier run au demarrage pour que le dashboard ne soit jamais vide.
    run = await Orchestrator(on_event=_broadcast).run(seed=SCENARIOS["long"]["seed"])
    JOURNAL.record(run)
    yield


app = FastAPI(
    title="Comite d'investissement Or - API",
    version="1.0.0-mvp",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # V1 locale ; a restreindre au domaine en prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "tools_connected": False,
        "note": "V1 — agents créés, outils non branchés",
    }


@app.get("/api/agents")
async def agents() -> dict:
    """Fiche des huit agents : mandat, outils prevus, etage du pipeline."""
    cards = registry.cards()
    return {
        "agents": [c.model_dump(mode="json") for c in cards],
        "total": len(cards),
        "llm_agents": sum(1 for a in registry.AGENTS if a.is_llm),
        "deterministic_agents": sum(1 for a in registry.AGENTS if not a.is_llm),
        "tools_total": sum(len(c.tools) for c in cards),
        "tools_connected": 0,
    }


@app.get("/api/market")
async def market(scenario: str = Query("long")) -> dict:
    """
    Etat de marche courant, calcule sans reveiller le moindre LLM.

    Le scenario doit etre le meme que celui du dernier run, sinon l'en-tete
    afficherait un prix different de celui sur lequel la decision a ete prise.
    """
    if scenario not in SCENARIOS:
        raise HTTPException(400, f"Scénario inconnu. Choix : {list(SCENARIOS)}")
    snap = build_market_snapshot(seed=SCENARIOS[scenario]["seed"])
    fv = snap["features"]
    return {
        "features": fv.model_dump(mode="json"),
        "reads": [
            {**r, "structure": r["structure"].value, "quality": r["quality"].value}
            for r in snap["reads"]
        ],
        "levels": snap["levels"],
        "sources": [s.model_dump(mode="json") for s in snap["sources"]],
        "calendar": [e.model_dump(mode="json") for e in snap["calendar"]],
        "triggers": [t.model_dump(mode="json") for t in snap["triggers"]],
        "change_pct": round(snap["change_pct"], 2),
        "candles": _candles(snap["frames"]["5m"], 120),
    }


def _candles(df, n: int) -> list[dict]:
    tail = df.tail(n)
    return [
        {
            "t": ts.isoformat(),
            "o": float(r.open), "h": float(r.high),
            "l": float(r.low), "c": float(r.close),
            "v": float(r.volume),
        }
        for ts, r in tail.iterrows()
    ]


@app.post("/api/run")
async def run_pipeline(
    scenario: str = Query("long", description="Scenario de demonstration"),
) -> dict:
    """
    Lance un run complet du comite.

    En production ce point d'entree correspond au bouton "Analyser maintenant" ;
    les runs automatiques viendront du detecteur de candidats deterministe.
    """
    if scenario not in SCENARIOS:
        raise HTTPException(400, f"Scénario inconnu. Choix : {list(SCENARIOS)}")

    run = await Orchestrator(on_event=_broadcast).run(
        trigger=manual_trigger(), seed=SCENARIOS[scenario]["seed"]
    )
    JOURNAL.record(run)
    return run.model_dump(mode="json")


@app.get("/api/runs")
async def runs(limit: int = 30) -> dict:
    return {"runs": [r.model_dump(mode="json") for r in JOURNAL.runs(limit)]}


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str) -> dict:
    run = JOURNAL.run(run_id)
    if not run:
        raise HTTPException(404, "Run introuvable")
    return run.model_dump(mode="json")


@app.get("/api/journal")
async def journal() -> dict:
    return {
        "entries": [e.model_dump(mode="json") for e in JOURNAL.entries()],
        "stats": JOURNAL.stats(),
        "calibration": [
            {**b.model_dump(), "observed_rate": b.observed_rate}
            for b in JOURNAL.calibration()
        ],
        # Ventilation par agent : c'est elle qui dira QUI ecouter.
        "by_agent": JOURNAL.agent_reliability(),
    }


@app.get("/api/scenarios")
async def scenarios() -> dict:
    return {"scenarios": [{"id": k, **v} for k, v in SCENARIOS.items()]}


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    """Avancement du pipeline en direct (SSE)."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.add(queue)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
