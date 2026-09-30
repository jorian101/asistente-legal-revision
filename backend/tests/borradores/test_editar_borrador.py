"""Test unitario para editar_borrador (CRUD-4): ejercita el repo real con sesión mockeada."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.borrador import BorradorModel
from src.adapters.postgres.repos.borrador_repo import BorradorRepoImpl


def _modelo(contenido: str = "original") -> BorradorModel:
    return BorradorModel(
        id=7,
        expediente_id=2,
        propietario_id=3,
        tipo="auto_vista_apelacion_incidental",
        estado="borrador",
        contenido=contenido,
        plantilla_usada="auto_vista_apelacion_incidental.md",
        contexto_recuperado=None,
        created_at=datetime(2026, 8, 9, 10, 0, 0),
        updated_at=None,
    )


def _session(modelo: BorradorModel | None) -> MagicMock:
    resultado = MagicMock()
    resultado.scalars.return_value.one_or_none.return_value = modelo
    session = MagicMock()
    session.execute = AsyncMock(return_value=resultado)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_actualizar_contenido_propietario_persiste_y_hace_commit():
    modelo = _modelo()
    session = _session(modelo)

    res = await BorradorRepoImpl(session).actualizar_contenido_propietario(
        7, propietario_id=3, contenido="Texto editado manualmente por el usuario."
    )

    assert res is not None
    assert res.contenido == "Texto editado manualmente por el usuario."
    assert modelo.contenido == "Texto editado manualmente por el usuario."
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_actualizar_contenido_propietario_filtra_por_propietario_y_estado():
    session = _session(None)

    res = await BorradorRepoImpl(session).actualizar_contenido_propietario(
        7, propietario_id=99, contenido="intento ajeno"
    )

    assert res is None
    session.commit.assert_not_awaited()
    where = str(session.execute.await_args.args[0].whereclause)
    assert "propietario_id" in where
    assert "estado" in where
