"""
Journal shadow / paper trading.

Le PDF est explicite : en V1 le CIO n'est pas connecte a l'execution. Le
systeme tourne en shadow avec journalisation complete, et c'est ce journal qui
permettra de determiner objectivement si le systeme apporte quelque chose,
quels agents contribuent reellement a la performance et lesquels donnent
simplement l'impression d'etre sophistiques.

Ajout issu du debat avec Hermes : la CALIBRATION. Le PDF precise que le score
de conviction est "la conviction interne du modele, pas une probabilite reelle
de gain". Tant qu'on ne la mesure pas, c'est un nombre decoratif. On stocke
donc des le premier run le bucket de conviction et l'issue reelle, pour tracer
la courbe conviction annoncee / taux de reussite observe.

V1 : stockage memoire. Le passage en Postgres (table append-only) ne change
que la couche de persistance, pas les structures.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import (
    CalibrationBucket,
    Direction,
    JournalEntry,
    Localized,
    Run,
    RunSummary,
)

BUCKET_EDGES = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]

# Seuils d'echantillon. En dessous, on affiche "pas mesurable" plutot qu'un
# pourcentage rassurant. Hermes : "un bucket avec 3 trades n'est pas fiable."
MIN_BUCKET_SAMPLE = 10      # par bucket de conviction
MIN_AGENT_SAMPLE = 30       # par agent, tous buckets confondus


class Journal:
    def __init__(self) -> None:
        self._runs: list[Run] = []
        self._entries: list[JournalEntry] = []

    # ------------------------------------------------------------------
    def record(self, run: Run) -> JournalEntry | None:
        self._runs.insert(0, run)
        self._runs = self._runs[:200]

        if run.decision is None:
            return None

        ticket = run.ticket
        entry = JournalEntry(
            run_id=run.run_id,
            timestamp=run.started_at,
            decision=run.decision,
            conviction=run.conviction or 0,
            risk_verdict=run.risk_verdict or "REJECT",
            spot=run.spot_at_decision or 0.0,
            outcome="NO_TRADE" if run.decision is Direction.NO_TRADE else "OPEN",
            agent_contributions={
                aid: (o.conviction or 0) for aid, o in run.outputs.items() if o.conviction
            },
            notes=Localized(
                fr=_note_fr(run),
                en=_note_en(run),
            ),
        )
        if ticket and run.decision is not Direction.NO_TRADE:
            entry.theoretical_entry = run.spot_at_decision
            entry.theoretical_stop = _extract_price(ticket.stop_logic.en)
            entry.theoretical_target = _extract_price(ticket.target_logic.en)

        self._entries.insert(0, entry)
        self._entries = self._entries[:500]
        return entry

    # ------------------------------------------------------------------
    def runs(self, limit: int = 30) -> list[RunSummary]:
        return [RunSummary(**r.model_dump(include=set(RunSummary.model_fields)))
                for r in self._runs[:limit]]

    def run(self, run_id: str) -> Run | None:
        return next((r for r in self._runs if r.run_id == run_id), None)

    def entries(self, limit: int = 50) -> list[JournalEntry]:
        return self._entries[:limit]

    # ------------------------------------------------------------------
    def calibration(self) -> list[CalibrationBucket]:
        """
        Conviction annoncee contre reussite observee.

        Tant que `n_trades` est faible, la courbe ne veut rien dire - c'est
        normal et l'UI doit le dire plutot que d'afficher un pourcentage
        rassurant calcule sur trois trades.
        """
        buckets = [CalibrationBucket(lower=lo, upper=hi) for lo, hi in BUCKET_EDGES]
        for e in self._entries:
            if e.outcome in ("OPEN", "NO_TRADE"):
                continue
            for b in buckets:
                if b.lower <= e.conviction < b.upper:
                    b.n_trades += 1
                    if e.outcome == "WIN":
                        b.n_wins += 1
                    break
        return buckets

    def calibration_by_agent(self) -> dict[str, list[CalibrationBucket]]:
        """
        Calibration ventilee PAR AGENT.

        Correction apportee par Hermes, et c'est la bonne : une courbe agregee
        ne sert a rien. Si l'agent technique est bien calibre (conviction 80 ->
        78 % de reussite) et l'agent macro mal calibre (80 -> 55 %), la moyenne
        fait croire que 80 vaut un intermediaire fiable, alors que le vrai
        signal est "ecoute la technique, ignore la macro".

        C'est cette colonne qui dira QUI ecouter, pas seulement a partir de
        quel seuil.
        """
        by_agent: dict[str, list[CalibrationBucket]] = {}

        for e in self._entries:
            if e.outcome in ("OPEN", "NO_TRADE"):
                continue
            for agent_id, conviction in e.agent_contributions.items():
                buckets = by_agent.setdefault(
                    agent_id,
                    [CalibrationBucket(lower=lo, upper=hi) for lo, hi in BUCKET_EDGES],
                )
                for b in buckets:
                    if b.lower <= conviction < b.upper:
                        b.n_trades += 1
                        if e.outcome == "WIN":
                            b.n_wins += 1
                        break

        return by_agent

    def agent_reliability(self) -> list[dict]:
        """
        Resume par agent, avec le garde-fou d'echantillon minimal.

        Un bucket a trois trades n'est pas une mesure. On le dit explicitement
        plutot que d'afficher un pourcentage qui inspire une confiance que la
        donnee ne justifie pas.
        """
        out = []
        for agent_id, buckets in self.calibration_by_agent().items():
            n = sum(b.n_trades for b in buckets)
            wins = sum(b.n_wins for b in buckets)
            usable = [b for b in buckets if b.n_trades >= MIN_BUCKET_SAMPLE]
            out.append({
                "agent_id": agent_id,
                "n_trades": n,
                "hit_rate": round(wins / n, 3) if n else None,
                "buckets": [
                    {**b.model_dump(), "observed_rate": b.observed_rate,
                     "reliable": b.n_trades >= MIN_BUCKET_SAMPLE}
                    for b in buckets
                ],
                "reliable_buckets": len(usable),
                "sample_sufficient": n >= MIN_AGENT_SAMPLE,
            })
        out.sort(key=lambda a: a["n_trades"], reverse=True)
        return out

    def stats(self) -> dict:
        decided = [e for e in self._entries if e.decision is not Direction.NO_TRADE]
        no_trade = [e for e in self._entries if e.decision is Direction.NO_TRADE]
        closed = [e for e in self._entries if e.outcome in ("WIN", "LOSS", "SCRATCH")]
        wins = [e for e in closed if e.outcome == "WIN"]

        return {
            "total_runs": len(self._entries),
            "decisions": len(decided),
            "no_trades": len(no_trade),
            "no_trade_rate": round(len(no_trade) / len(self._entries) * 100, 1)
            if self._entries else 0.0,
            "closed": len(closed),
            "hit_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
            "avg_conviction": round(
                sum(e.conviction for e in decided) / len(decided), 1
            ) if decided else None,
            # En dessous de ce seuil, toute statistique de reussite est du bruit.
            "sample_sufficient": len(closed) >= 30,
        }


_TRIGGER_FR = {
    "MANUAL": "Demande manuelle",
    "SETUP_CANDIDATE": "Setup détecté",
    "SCHEDULED": "Analyse planifiée",
    "EVENT_WINDOW": "Fenêtre macro",
}
_TRIGGER_EN = {
    "MANUAL": "Manual request",
    "SETUP_CANDIDATE": "Setup detected",
    "SCHEDULED": "Scheduled run",
    "EVENT_WINDOW": "Macro window",
}


def _note_fr(run: Run) -> str:
    """Formulation lisible : l'utilisateur ne doit pas lire d'enum brute."""
    t = _TRIGGER_FR.get(run.trigger.value, run.trigger.value)
    return f"{t}, pipeline interrompu" if run.halted else f"{t}, analyse complète"


def _note_en(run: Run) -> str:
    t = _TRIGGER_EN.get(run.trigger.value, run.trigger.value)
    return f"{t}, pipeline halted" if run.halted else f"{t}, full analysis"


def _extract_price(text: str) -> float | None:
    """Recupere le premier nombre decimal d'une phrase generee."""
    import re
    m = re.search(r"\d{3,5}\.\d{1,2}", text)
    return float(m.group()) if m else None


JOURNAL = Journal()
