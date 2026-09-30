"""Tests unitarios del use case AjustarParametrosRAG (HU-23)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.admin.ajustar_parametros_rag import ejecutar
from src.domain.entities.configuracion_rag import ConfiguracionRAG


def _cfg() -> ConfiguracionRAG:
    return ConfiguracionRAG(
        id=1,
        score_threshold=0.6,
        top_k_denso=40,
        top_k_lexico=20,
        top_k_final=10,
        modelo_embeddings="nomic-embed-text",
        modelo_llm_default="llama3:8b",
        actualizado_por=7,
    )


def _repo_mock() -> AsyncMock:
    repo = AsyncMock()
    repo.actualizar = AsyncMock(return_value=_cfg())
    return repo


@pytest.mark.asyncio
async def test_ajuste_valido_delega_al_repo_con_valores_limpios() -> None:
    repo = _repo_mock()

    cfg = await ejecutar(repo, {"top_k_final": 10, "score_threshold": 0.55}, 7)

    repo.actualizar.assert_awaited_once_with(
        {"top_k_final": 10, "score_threshold": 0.55}, actualizado_por=7
    )
    assert cfg.top_k_final == 10


@pytest.mark.asyncio
async def test_ajuste_vacio_rechazado_sin_llamar_repo() -> None:
    repo = _repo_mock()

    with pytest.raises(ValueError, match="ningún parámetro válido"):
        await ejecutar(repo, {}, 7)

    repo.actualizar.assert_not_awaited()


@pytest.mark.asyncio
async def test_ajuste_fuera_de_rango_propaga_value_error() -> None:
    repo = _repo_mock()

    with pytest.raises(ValueError, match="top_k_final"):
        await ejecutar(repo, {"top_k_final": 999}, 7)

    repo.actualizar.assert_not_awaited()
