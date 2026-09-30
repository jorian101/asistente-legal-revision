"""Test unitario para editar_expediente (CRUD-3)."""

from unittest.mock import AsyncMock

import pytest

from src.domain.entities.expediente import Expediente


@pytest.mark.asyncio
async def test_actualizar_expediente_repo():
    expediente_repo = AsyncMock()
    exp_modificado = Expediente(
        id=5,
        numero_caso="EXP-2026-MOD",
        tipo_proceso="consulta",
        tribunal_origen="Tribunal Supremo Military 1",
        procesado_nombre="Juan Pérez Modificado",
        delito="Insubordinación Grave",
        abierto_por=1,
    )
    expediente_repo.actualizar.return_value = exp_modificado

    res = await expediente_repo.actualizar(
        5,
        numero_caso="EXP-2026-MOD",
        procesado_nombre="Juan Pérez Modificado",
        delito="Insubordinación Grave",
    )

    assert res.numero_caso == "EXP-2026-MOD"
    assert res.procesado_nombre == "Juan Pérez Modificado"
    assert res.delito == "Insubordinación Grave"
    expediente_repo.actualizar.assert_called_once_with(
        5,
        numero_caso="EXP-2026-MOD",
        procesado_nombre="Juan Pérez Modificado",
        delito="Insubordinación Grave",
    )
