"""Test unitario para use case eliminar_obra (CRUD-1)."""

from unittest.mock import AsyncMock

import pytest

from src.application.expedientes.eliminar_obra import (
    ObraNoPropiaError,
    eliminar_obra,
)
from src.domain.entities.obra import Obra


@pytest.mark.asyncio
async def test_eliminar_obra_exito():
    obra_repo = AsyncMock()
    fragmento_repo = AsyncMock()
    vector_repo = AsyncMock()

    obra = Obra(
        id=10,
        expediente_id=1,
        propietario_id=5,
        tipo_documento="auto_vista",
        nombre_archivo="auto.pdf",
        contenido_texto="texto",
        estado_visibilidad="privado",
        fuente="manual",
    )
    obra_repo.obtener.return_value = obra
    obra_repo.eliminar.return_value = True

    resultado = await eliminar_obra(
        obra_repo,
        fragmento_repo,
        vector_repo,
        expediente_id=1,
        obra_id=10,
        solicitante_id=5,
        es_admin=False,
    )

    assert resultado is True
    vector_repo.delete_by_obra.assert_called_once_with(10)
    fragmento_repo.delete_by_obra.assert_called_once_with(10)
    obra_repo.eliminar.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_eliminar_obra_no_propia_lanza_error():
    obra_repo = AsyncMock()
    fragmento_repo = AsyncMock()
    vector_repo = AsyncMock()

    obra = Obra(
        id=10,
        expediente_id=1,
        propietario_id=5,
        tipo_documento="auto_vista",
        nombre_archivo="auto.pdf",
        contenido_texto="texto",
        estado_visibilidad="privado",
        fuente="manual",
    )
    obra_repo.obtener.return_value = obra

    with pytest.raises(ObraNoPropiaError):
        await eliminar_obra(
            obra_repo,
            fragmento_repo,
            vector_repo,
            expediente_id=1,
            obra_id=10,
            solicitante_id=99,
            es_admin=False,
        )
