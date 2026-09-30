"""Aviso cuando SECRET_KEY es corta para firmar JWT HS256 (F-15)."""

from __future__ import annotations

from src.config import Settings


def _settings():
    # Settings esta decorada con lru_cache: __wrapped__ construye una instancia nueva.
    return Settings.__wrapped__()  # type: ignore[attr-defined]


def test_secret_key_corta_emite_aviso(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SECRET_KEY", "corta")

    with caplog.at_level("WARNING"):
        cfg = _settings()

    assert cfg.secret_key == "corta"  # no bloquea el arranque
    assert "SECRET_KEY" in caplog.text


def test_secret_key_larga_no_emite_aviso(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SECRET_KEY", "x" * 32)

    with caplog.at_level("WARNING"):
        _settings()

    assert "SECRET_KEY" not in caplog.text
