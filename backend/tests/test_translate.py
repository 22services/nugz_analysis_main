"""Tests du traducteur : aucun appel réseau (fournisseur simulé)."""
from __future__ import annotations

import pytest

from app import translate as tr


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "CACHE_FILE", tmp_path / "t.json")
    monkeypatch.setattr(tr, "_cache", {})
    monkeypatch.setattr(tr, "_loaded", True)
    monkeypatch.setattr(tr, "_blocked_until", {})
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)


def test_translates_and_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(tr, "_mymemory", lambda t, lang: calls.append(t) or f"FR:{t}")
    r1 = tr.translate_many(["Gold falls", "Gold falls", "Oil rises"])
    assert r1["texts"] == ["FR:Gold falls", "FR:Gold falls", "FR:Oil rises"]
    assert r1["translated"] == [True, True, True]
    assert sorted(calls) == ["Gold falls", "Oil rises"]           # doublon : un seul appel
    tr.translate_many(["Gold falls"])
    assert len(calls) == 2                                         # relu depuis le cache
    assert tr.CACHE_FILE.exists()                                  # et persisté


def test_failure_returns_original_text(monkeypatch):
    monkeypatch.setattr(tr, "_mymemory", lambda t, lang: None)
    r = tr.translate_many(["Gold falls"])
    assert r["texts"] == ["Gold falls"] and r["translated"] == [False]


def test_quota_warning_is_never_shown_as_a_title(monkeypatch):
    class R:  # simule la réponse HTTP 200 « quota épuisé » de MyMemory
        pass
    monkeypatch.setattr(tr, "_open", lambda req: {
        "responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY"},
        "quotaFinished": False, "responseStatus": 200})
    assert tr._mymemory("Gold falls", "fr") is None
    assert not tr._active("mymemory")                              # fournisseur suspendu


def test_html_entities_are_decoded(monkeypatch):
    monkeypatch.setattr(tr, "_open", lambda req: {
        "responseData": {"translatedText": "L&#39;or recule"}, "responseStatus": 200})
    assert tr._mymemory("Gold falls", "fr") == "L'or recule"
