"""QDRANT_API_KEY opcional: si se define, todos los clientes Qdrant del backend la usan (F-26).

Los scripts de sync esperan una API key en el Qdrant del server, pero el backend
nunca la enviaba. Sin la variable el comportamiento no cambia (api_key=None).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.adapters.salud_sistema import SaludSistemaImpl
from src.config import Settings


def _settings():
    return Settings.__wrapped__()  # type: ignore[attr-defined]


def test_settings_lee_la_api_key_si_existe(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_API_KEY", "clave-secreta")

    assert _settings().qdrant_api_key == "clave-secreta"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_settings_sin_api_key_es_none(monkeypatch, valor) -> None:
    if valor is None:
        monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    else:
        monkeypatch.setenv("QDRANT_API_KEY", valor)

    assert _settings().qdrant_api_key is None


@pytest.mark.parametrize("clave", ["clave-secreta", None])
def test_el_repo_pasa_la_api_key_del_settings_al_cliente(clave) -> None:
    ajustes = SimpleNamespace(qdrant_url="http://q:6333", qdrant_api_key=clave, embedding_dim=8)
    with (
        patch("src.adapters.qdrant.qdrant_corpus_repo.get_settings", return_value=ajustes),
        patch("src.adapters.qdrant.qdrant_corpus_repo.QdrantClient") as cliente,
    ):
        QdrantCorpusRepo()

    assert cliente.call_args.kwargs["api_key"] == clave


def test_una_api_key_explicita_gana_sobre_el_settings() -> None:
    ajustes = SimpleNamespace(
        qdrant_url="http://q:6333", qdrant_api_key="del-settings", embedding_dim=8
    )
    with (
        patch("src.adapters.qdrant.qdrant_corpus_repo.get_settings", return_value=ajustes),
        patch("src.adapters.qdrant.qdrant_corpus_repo.QdrantClient") as cliente,
    ):
        QdrantCorpusRepo(api_key="explicita")

    assert cliente.call_args.kwargs["api_key"] == "explicita"


@pytest.mark.asyncio
async def test_el_ping_de_salud_tambien_usa_la_api_key() -> None:
    ajustes = SimpleNamespace(qdrant_url="http://q:6333", qdrant_api_key="clave-secreta")
    cliente = MagicMock()
    cliente.get_collection.return_value = SimpleNamespace(points_count=3)
    with (
        patch("src.adapters.salud_sistema.get_settings", return_value=ajustes),
        patch("qdrant_client.QdrantClient", return_value=cliente) as ctor,
    ):
        await SaludSistemaImpl(MagicMock())._ping_qdrant()

    assert ctor.call_args.kwargs["api_key"] == "clave-secreta"
