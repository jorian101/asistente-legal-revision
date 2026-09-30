"""Norma con propietario y estado de visibilidad (flujo privada -> global -> aprobacion)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.norma import NormaModel
from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
from src.domain.entities.norma import Norma


def _session(model=None):
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = model
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _model(**kw):
    base = {
        "id": 3,
        "nombre": "Libro",
        "abreviatura": "LIB-X",
        "tipo": "doctrina_libro",
        "jerarquia": "doctrina",
        "version": None,
        "ruta_archivo": None,
        "indexado": True,
        "indexado_por": None,
        "activo": True,
        "created_at": None,
        "propietario_id": 10,
        "estado_visibilidad": "privado",
        "motivo_rechazo": None,
        "origen_obra_id": None,
    }
    m = NormaModel()
    for k, v in {**base, **kw}.items():
        setattr(m, k, v)
    return m


def test_la_entidad_por_defecto_es_global_y_sin_propietario():
    n = Norma(id=None, nombre="CPE", abreviatura="CPE", tipo="constitucion", jerarquia="suprema")

    assert n.estado_visibilidad == "global"
    assert n.propietario_id is None


@pytest.mark.asyncio
async def test_save_persiste_propietario_y_estado():
    session = _session()
    norma = Norma(
        id=None,
        nombre="Libro",
        abreviatura="LIB-X",
        tipo="doctrina_libro",
        jerarquia="doctrina",
        propietario_id=10,
        estado_visibilidad="privado",
    )

    await SqlNormaRepo(session).save(norma)

    modelo = session.add.call_args.args[0]
    assert modelo.propietario_id == 10
    assert modelo.estado_visibilidad == "privado"


@pytest.mark.asyncio
async def test_get_by_id_devuelve_los_campos_nuevos():
    norma = await SqlNormaRepo(_session(_model())).get_by_id(3)

    assert norma is not None
    assert (norma.propietario_id, norma.estado_visibilidad) == (10, "privado")


@pytest.mark.asyncio
async def test_actualizar_visibilidad_guarda_estado_y_motivo():
    modelo = _model()
    session = _session(modelo)

    norma = await SqlNormaRepo(session).actualizar_visibilidad(3, "rechazado", "no es libro")

    assert modelo.estado_visibilidad == "rechazado"
    assert modelo.motivo_rechazo == "no es libro"
    session.commit.assert_awaited_once()
    assert norma is not None


@pytest.mark.asyncio
async def test_actualizar_visibilidad_de_norma_inexistente_devuelve_none():
    assert await SqlNormaRepo(_session(None)).actualizar_visibilidad(9, "global") is None
