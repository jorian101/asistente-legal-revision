"""Validacion de esquema de EMBEDDING/RERANKER/LLM_ENDPOINTS y de env numericos (F-21)."""

from __future__ import annotations

import json

import pytest

from src.config import Settings


def _settings():
    # Settings esta decorada con lru_cache: __wrapped__ construye una instancia nueva.
    return Settings.__wrapped__()  # type: ignore[attr-defined]


EMB_OK = {"id": "e1", "provider": "ollama", "base_url": "http://x", "model": "m", "dim": 8}
RER_OK = {"id": "r1", "provider": "http", "base_url": "http://x", "model": "m"}
LLM_OK = {"id": "l1", "provider": "ollama", "base_url": "http://x", "model": "m"}


@pytest.mark.parametrize(
    "var,valido",
    [
        ("EMBEDDING_ENDPOINTS", [EMB_OK]),
        ("RERANKER_ENDPOINTS", [RER_OK]),
        ("LLM_ENDPOINTS", [LLM_OK]),
    ],
)
def test_endpoints_validos_arrancan(monkeypatch, var, valido) -> None:
    monkeypatch.setenv(var, json.dumps(valido))

    _settings()  # no lanza


@pytest.mark.parametrize(
    "var,invalido,fragmento",
    [
        ("EMBEDDING_ENDPOINTS", {"id": "e1"}, "lista"),  # dict en vez de lista
        ("EMBEDDING_ENDPOINTS", [{"id": "e1", "provider": "ollama"}], "base_url"),
        ("EMBEDDING_ENDPOINTS", [{**EMB_OK, "dim": "ocho"}], "dim"),
        ("RERANKER_ENDPOINTS", ["no-es-dict"], "objeto"),
        ("RERANKER_ENDPOINTS", [{"id": "r1", "provider": "http", "model": "m"}], "base_url"),
        ("LLM_ENDPOINTS", [{"provider": "ollama", "base_url": "http://x", "model": "m"}], "id"),
    ],
)
def test_endpoints_mal_formados_fallan_nombrando_la_variable(
    monkeypatch, var, invalido, fragmento
) -> None:
    monkeypatch.setenv(var, json.dumps(invalido))

    with pytest.raises(RuntimeError) as exc:
        _settings()

    assert var in str(exc.value)
    assert fragmento in str(exc.value)


def test_env_entero_invalido_nombra_la_variable(monkeypatch) -> None:
    monkeypatch.setenv("PG_POOL_SIZE", "diez")

    with pytest.raises(RuntimeError, match="PG_POOL_SIZE"):
        _settings()
