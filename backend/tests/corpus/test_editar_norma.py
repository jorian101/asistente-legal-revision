"""Test unitario / router para editar_norma (CRUD-2)."""

from unittest.mock import AsyncMock

import pytest

from src.domain.entities.norma import Norma


@pytest.mark.asyncio
async def test_editar_norma_repo():
    norma_repo = AsyncMock()
    norma_actualizada = Norma(
        id=1,
        abreviatura="CPE",
        nombre="Constitución Política del Estado Modificada",
        tipo="ley",
        jerarquia="constitucional",
        version="2026-v2",
        indexado=True,
    )
    norma_repo.actualizar.return_value = norma_actualizada

    res = await norma_repo.actualizar(
        1,
        nombre="Constitución Política del Estado Modificada",
        version="2026-v2",
    )

    assert res.nombre == "Constitución Política del Estado Modificada"
    assert res.version == "2026-v2"
    norma_repo.actualizar.assert_called_once_with(
        1,
        nombre="Constitución Política del Estado Modificada",
        version="2026-v2",
    )
