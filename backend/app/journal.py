"""
Journal des décisions : le vrai instrument de mesure.

Chaque décision de 15 minutes est enregistrée puis NOTÉE sur les barres
suivantes, avec des règles réalistes pour des données gratuites différées :

  - entrée théorique = clôture de la barre qui suit la barre décidée
    (premier prix exécutable après publication, ~10-13 min de délai) ;
  - si ce prix a déjà dépassé la limite « ne pas courir après » du ticket,
    ou touché le stop, le trade est MISSED (non pris) ;
  - ensuite : premier touché du stop ou de l'objectif 1. Si les deux sont
    touchés dans la même barre, on compte une PERTE (hypothèse prudente) ;
  - stop temporel : sortie à la clôture après MAX_HOLD_BARS barres ;
  - coûts déduits en R (spread + glissement).

Deux sources : `live` (décisions prises en temps réel) et `replay`
(le même moteur rejoué barre par barre sur l'historique, sans look-ahead).
On ne les mélange jamais dans les statistiques.

Persistance : un fichier JSONL sur un volume Docker. Le journal survit aux
redémarrages.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from app.committee import MAX_HOLD_BARS, STEP
from app.patterns import COST_FRAC, wilson

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
MIN_SAMPLE = 30


class Journal:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "decisions.jsonl"
        self.latest_path = self.path.with_name("latest.json")
        self._lock = threading.Lock()
        self.entries: dict[str, dict] = {}       # clé : source|bar_start
        self.latest: dict | None = None
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                for line in self.path.read_text().splitlines():
                    if line.strip():
                        e = json.loads(line)
                        self.entries[self._key(e)] = e
            if self.latest_path.exists():
                self.latest = json.loads(self.latest_path.read_text())
        except Exception:
            # Un journal corrompu ne doit pas empêcher le service de démarrer.
            pass

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as fh:
            for e in sorted(self.entries.values(), key=lambda e: e["bar_start"]):
                fh.write(json.dumps(e) + "\n")
        tmp.replace(self.path)

    @staticmethod
    def _key(e: dict) -> str:
        return f"{e['source']}|{e['bar_start']}"

    def has(self, source: str, bar_start: str) -> bool:
        return f"{source}|{bar_start}" in self.entries

    # ------------------------------------------------------------------
    def record(self, d: dict, source: str, persist: bool = True) -> None:
        r = d["risk"]
        e = {
            "source": source, "bar_start": d["bar_start"], "bar_end": d["bar_end"],
            "decided_at": d["decided_at"], "decision": d["decision"],
            "reason": d["reason"], "conviction": d["conviction"],
            "price": d["market"]["price"], "regime": d["market"]["regime"],
            "session": d["market"]["session"], "raw_score": d["cio"]["raw_score"],
            "scores": {a["id"]: a["score"] for a in d["agents"]},
            "entry_ref": r["entry"], "stop": r["stop"], "t1": r["t1"], "t2": r["t2"],
            "chase_limit": r["chase_limit"], "rr1": r["rr1"],
            "outcome": "NO_TRADE" if d["decision"] == "NO_TRADE" else "OPEN",
            "entry": None, "exit": None, "exit_at": None, "pnl_r": None,
        }
        with self._lock:
            self.entries[self._key(e)] = e
            if source == "live":
                self.latest = d
                try:
                    self.latest_path.write_text(json.dumps(d))
                except OSError:
                    pass
            if persist:
                self._flush()

    def flush(self) -> None:
        with self._lock:
            self._flush()

    # ------------------------------------------------------------------
    def evaluate(self, m15: pd.DataFrame) -> int:
        """Note les trades encore OPEN avec les barres closes disponibles."""
        changed = 0
        with self._lock:
            for e in self.entries.values():
                if e["outcome"] == "OPEN" and _score(e, m15):
                    changed += 1
            if changed:
                self._flush()
        return changed

    # ------------------------------------------------------------------
    def history(self, source: str, limit: int = 200) -> list[dict]:
        with self._lock:
            items = sorted((dict(e) for e in self.entries.values() if e["source"] == source),
                           key=lambda e: e["bar_start"])
        taken = {id(e) for e in _one_at_a_time(items)}
        for e in items:
            e["taken"] = id(e) in taken
        return items[::-1][:limit]

    def stats(self, source: str) -> dict:
        with self._lock:
            items = sorted((e for e in self.entries.values() if e["source"] == source),
                           key=lambda e: e["bar_start"])
        signals = [e for e in items if e["decision"] != "NO_TRADE"]
        trades = _one_at_a_time(items)
        closed = [e for e in trades if e["outcome"] in ("WIN", "LOSS", "SCRATCH")]
        wins = [e for e in closed if (e["pnl_r"] or 0) > 0]
        pnl = [e["pnl_r"] for e in closed if e["pnl_r"] is not None]
        lo, hi = wilson(len(wins), len(closed)) if closed else (None, None)
        first = min((e["bar_start"] for e in items), default=None)
        last = max((e["bar_start"] for e in items), default=None)
        # Facteur de profit et pire série : ce que le compte ressent vraiment.
        gross_w = sum(p for p in pnl if p > 0)
        gross_l = -sum(p for p in pnl if p < 0)
        streak = worst = 0
        for p in pnl:
            streak = streak + 1 if p <= 0 else 0
            worst = max(worst, streak)
        return {
            "source": source, "decisions": len(items), "signals": len(signals),
            "trades": len(trades), "in_position_skipped": len(signals) - len(trades),
            "no_trade_rate": round(1 - len(signals) / len(items), 3) if items else None,
            "closed": len(closed), "open": sum(e["outcome"] == "OPEN" for e in trades),
            "missed": sum(e["outcome"] == "MISSED" for e in trades),
            "wins": len(wins), "losses": len(closed) - len(wins),
            "hit_rate": round(len(wins) / len(closed), 3) if closed else None,
            "hit_ci": [round(lo, 3), round(hi, 3)] if closed else None,
            "expectancy_r": round(float(np.mean(pnl)), 3) if pnl else None,
            # IC 95 % de l'espérance : s'il contient 0, aucun avantage prouvé.
            "expectancy_ci": ([round(float(np.mean(pnl) - 1.96 * np.std(pnl, ddof=1) / np.sqrt(len(pnl))), 3),
                               round(float(np.mean(pnl) + 1.96 * np.std(pnl, ddof=1) / np.sqrt(len(pnl))), 3)]
                              if len(pnl) > 1 else None),
            "total_r": round(float(np.sum(pnl)), 2) if pnl else None,
            "profit_factor": round(gross_w / gross_l, 2) if gross_l > 0 else None,
            "worst_losing_streak": worst,
            "sample_sufficient": len(closed) >= MIN_SAMPLE,
            "from": first, "to": last,
            "by_direction": {
                d: _mini([e for e in closed if e["decision"] == d]) for d in ("LONG", "SHORT")
            },
        }


def _one_at_a_time(items: list[dict]) -> list[dict]:
    """
    Une position à la fois. Le comité peut répéter « SHORT » à chaque quart
    d'heure d'une même tendance : compter chaque répétition comme un trade
    fabriquerait des dizaines d'observations corrélées (pseudo-réplication).
    Un signal reçu pendant qu'une position est ouverte est ignoré ; un signal
    MISSED ne bloque rien.
    """
    trades, busy_until = [], ""
    for e in items:
        if e["decision"] == "NO_TRADE" or e["bar_end"] < busy_until:
            continue
        trades.append(e)
        if e["outcome"] == "OPEN":
            busy_until = "9999"
        elif e["outcome"] in ("WIN", "LOSS", "SCRATCH"):
            busy_until = e["exit_at"]
    return trades


def _mini(items: list[dict]) -> dict:
    pnl = [e["pnl_r"] for e in items if e["pnl_r"] is not None]
    return {"n": len(items),
            "hit_rate": round(sum(p > 0 for p in pnl) / len(pnl), 3) if pnl else None,
            "expectancy_r": round(float(np.mean(pnl)), 3) if pnl else None}


def _score(e: dict, m15: pd.DataFrame) -> bool:
    """Met à jour `e` si l'issue est connue. Renvoie True si modifié."""
    d = 1 if e["decision"] == "LONG" else -1
    after = m15[m15.index >= pd.Timestamp(e["bar_end"])]
    if after.empty:
        return False
    fill = after.iloc[0]
    entry = float(fill["close"])
    stop, t1 = e["stop"], e["t1"]
    # Trop tard : le prix a filé au-delà de la limite, ou le stop est déjà touché.
    beyond_chase = (entry - e["chase_limit"]) * d > 0
    stop_hit = (fill["low"] <= stop) if d > 0 else (fill["high"] >= stop)
    if beyond_chase or stop_hit or (entry - t1) * d >= 0:
        e.update(outcome="MISSED", entry=round(entry, 2))
        return True
    risk = abs(entry - stop)
    cost_r = COST_FRAC * entry / risk if risk else 0.0
    path = after.iloc[1:1 + MAX_HOLD_BARS]
    for ts, b in path.iterrows():
        hit_s = b["low"] <= stop if d > 0 else b["high"] >= stop
        hit_t = b["high"] >= t1 if d > 0 else b["low"] <= t1
        if hit_s:                                    # prudence si les deux
            e.update(outcome="LOSS", entry=round(entry, 2), exit=stop,
                     exit_at=(ts + STEP).isoformat(), pnl_r=round(-1 - cost_r, 3))
            return True
        if hit_t:
            e.update(outcome="WIN", entry=round(entry, 2), exit=t1,
                     exit_at=(ts + STEP).isoformat(),
                     pnl_r=round(abs(t1 - entry) / risk - cost_r, 3))
            return True
    if len(path) >= MAX_HOLD_BARS:
        last_ts, last = path.index[-1], path.iloc[-1]
        r = d * (float(last["close"]) - entry) / risk - cost_r
        e.update(outcome="SCRATCH", entry=round(entry, 2), exit=round(float(last["close"]), 2),
                 exit_at=(last_ts + STEP).isoformat(), pnl_r=round(r, 3))
        return True
    return False


JOURNAL = Journal()
