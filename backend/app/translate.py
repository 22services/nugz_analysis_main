"""
Traduction des titres d'actualité (anglais -> français).

Les fournisseurs gratuits d'actualités ne publient qu'en anglais. Ce module
traduit seulement les TITRES (données publiques : aucune donnée personnelle
ne part vers le service), avec trois garde-fous :

1. **Cache persistant.** Un titre n'est traduit qu'une fois, puis relu sur
   disque (volume Docker) : le quota gratuit n'est consommé que par les
   titres réellement nouveaux, et les redémarrages ne le gaspillent pas.

2. **Fournisseurs.**
   - DeepL si `DEEPL_API_KEY` est défini (meilleure qualité ; offre gratuite
     de 500 000 caractères / mois) ;
   - sinon MyMemory, API officielle gratuite et sans clé (5 000 caractères
     par jour ; 50 000 si `MYMEMORY_EMAIL` est défini).
   L'endpoint « gtx » de Google est volontairement écarté : non officiel et
   bloqué par CAPTCHA dès qu'il est utilisé depuis un serveur.

3. **Dégradation douce.** Quota épuisé, timeout, erreur : on renvoie le
   titre d'origine, jamais une erreur, et on suspend le fournisseur un moment.
"""
from __future__ import annotations

import html
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CACHE_FILE = DATA_DIR / "translations.json"
MAX_CACHE = 5000
TIMEOUT_S = 8
BACKOFF_S = 3600                       # suspension d'un fournisseur en échec / quota atteint

_lock = threading.Lock()
_cache: dict[str, str] = {}
_loaded = False
_blocked_until: dict[str, float] = {}


# --------------------------------------------------------------------------
def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if CACHE_FILE.exists():
            _cache.update(json.loads(CACHE_FILE.read_text()))
    except Exception:
        pass                            # cache corrompu : on repart de zéro


def _save() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_cache, ensure_ascii=False))
        tmp.replace(CACHE_FILE)
    except OSError:
        pass


def _open(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Fournisseurs : chacun renvoie une traduction, ou None (échec / quota)
# --------------------------------------------------------------------------
def _mymemory(text: str, target: str) -> str | None:
    q = {"q": text[:480], "langpair": f"en|{target}"}
    if os.getenv("MYMEMORY_EMAIL"):
        q["de"] = os.environ["MYMEMORY_EMAIL"]
    req = urllib.request.Request(
        "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(q),
        headers={"User-Agent": "dashboard-translator/1.0"})
    try:
        d = _open(req)
    except Exception:
        return None
    out = (d.get("responseData") or {}).get("translatedText") or ""
    # Quota épuisé : MyMemory répond 200 avec un message d'avertissement
    # À LA PLACE de la traduction. Ne jamais l'afficher comme un titre.
    if d.get("quotaFinished") or "MYMEMORY WARNING" in out.upper() or d.get("responseStatus") != 200:
        _blocked_until["mymemory"] = time.time() + BACKOFF_S
        return None
    out = html.unescape(out).strip()
    return out or None


def _deepl_batch(texts: list[str], target: str) -> list[str | None]:
    key = os.environ["DEEPL_API_KEY"]
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    body = json.dumps({"text": texts, "source_lang": "EN", "target_lang": target.upper()}).encode()
    req = urllib.request.Request(
        f"https://{host}/v2/translate", data=body, method="POST",
        headers={"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json",
                 "User-Agent": "dashboard-translator/1.0"})
    try:
        d = _open(req)
        return [t.get("text") for t in d["translations"]]
    except Exception:
        _blocked_until["deepl"] = time.time() + BACKOFF_S
        return [None] * len(texts)


def _active(name: str) -> bool:
    return time.time() >= _blocked_until.get(name, 0)


def provider_name() -> str:
    return "deepl" if os.getenv("DEEPL_API_KEY") else "mymemory"


# --------------------------------------------------------------------------
def translate_many(texts: list[str], target: str = "fr") -> dict:
    """
    Traduit une liste de titres. Renvoie
    {"texts": [...], "translated": [bool, ...], "provider": str}
    dans le même ordre ; un titre non traduit est renvoyé tel quel.
    """
    with _lock:
        _load()
        hits = {t: _cache.get(f"{target}|{t}") for t in texts}
    todo = [t for t in dict.fromkeys(texts) if t and not hits.get(t)]
    provider = provider_name()
    fresh: dict[str, str] = {}

    if todo:
        if provider == "deepl" and _active("deepl"):
            for t, out in zip(todo, _deepl_batch(todo, target)):
                if out:
                    fresh[t] = out
        elif provider == "mymemory" and _active("mymemory"):
            with ThreadPoolExecutor(max_workers=5) as pool:
                for t, out in zip(todo, pool.map(lambda x: _mymemory(x, target), todo)):
                    if out:
                        fresh[t] = out
        if fresh:
            with _lock:
                for t, out in fresh.items():
                    _cache[f"{target}|{t}"] = out
                while len(_cache) > MAX_CACHE:
                    _cache.pop(next(iter(_cache)))
                _save()

    out_texts, flags = [], []
    for t in texts:
        tr_ = hits.get(t) or fresh.get(t)
        out_texts.append(tr_ or t)
        flags.append(bool(tr_) and tr_ != t)
    return {"texts": out_texts, "translated": flags, "provider": provider}
