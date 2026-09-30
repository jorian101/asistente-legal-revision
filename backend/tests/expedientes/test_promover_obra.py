"""Promoción de un obrado publicado a jurisprudencia (operador propone, supervisor aprueba)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.expedientes.promover_obra import (
    ObraNoEncontradaError,
    ObraNoPromovibleError,
    PromoverObra,
)


def _obra(**kw):
    base = {
        "id": 5,
        "propietario_id": 10,
        "tipo_documento": "sentencia",
        "estado_visibilidad": "publicado",
        "estado_validacion": None,
        "activo": True,
    }
    return SimpleNamespace(**{**base, **kw})


def _uc(obra):
    obra_repo = MagicMock()
    obra_repo.obtener = AsyncMock(return_value=obra)
    obra_repo.marcar_promocion = AsyncMock(
        side_effect=lambda obra_id, estado, motivo=None: SimpleNamespace(
            id=obra_id, estado_validacion=estado
        )
    )
    obra_repo.promover_a_jurisprudencia = AsyncMock(
        return_value=SimpleNamespace(
            id=5, tipo_documento="jurisprudencia", estado_visibilidad="global"
        )
    )
    vector_repo = MagicMock()
    vector_repo.actualizar_payload_obra = AsyncMock()
    return PromoverObra(obra_repo, vector_repo), obra_repo, vector_repo


@pytest.mark.asyncio
async def test_el_operador_propone_y_queda_pendiente():
    uc, obra_repo, _ = _uc(_obra())

    await uc.proponer(obra_id=5, usuario_id=10)

    obra_repo.marcar_promocion.assert_awaited_once_with(5, "promocion_pendiente")


@pytest.mark.asyncio
async def test_solo_el_dueno_propone():
    uc, obra_repo, _ = _uc(_obra(propietario_id=99))

    with pytest.raises(PermissionError):
        await uc.proponer(obra_id=5, usuario_id=10)
    obra_repo.marcar_promocion.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cambios",
    [
        {"estado_visibilidad": "privado"},  # hay que publicarlo antes
        {"tipo_documento": "doctrina"},  # doctrina no es un obrado
        {"tipo_documento": "jurisprudencia"},  # ya es jurisprudencia
        {"estado_validacion": "promocion_pendiente"},  # ya propuesto
        {"estado_validacion": "promovida"},
    ],
)
async def test_no_se_propone_lo_que_no_es_promovible(cambios):
    uc, _, _ = _uc(_obra(**cambios))

    with pytest.raises(ObraNoPromovibleError):
        await uc.proponer(obra_id=5, usuario_id=10)


@pytest.mark.asyncio
async def test_obra_inexistente_o_ajena():
    uc, _, _ = _uc(None)

    with pytest.raises(ObraNoEncontradaError):
        await uc.proponer(obra_id=5, usuario_id=10)


@pytest.mark.asyncio
async def test_el_supervisor_aprueba_y_se_actualiza_qdrant():
    uc, obra_repo, vector_repo = _uc(_obra(estado_validacion="promocion_pendiente"))

    await uc.resolver(obra_id=5, aprobar=True, actor_id=20)

    obra_repo.promover_a_jurisprudencia.assert_awaited_once_with(5)
    vector_repo.actualizar_payload_obra.assert_awaited_once_with(
        5,
        {
            "tipo_documento": "jurisprudencia",
            "tipo_fuente": "jurisprudencia",
            "visibilidad": "global",
        },
    )


@pytest.mark.asyncio
async def test_el_supervisor_rechaza_con_motivo():
    uc, obra_repo, vector_repo = _uc(_obra(estado_validacion="promocion_pendiente"))

    await uc.resolver(obra_id=5, aprobar=False, actor_id=20, motivo="No es vinculante")

    obra_repo.marcar_promocion.assert_awaited_once_with(
        5, "promocion_rechazada", "No es vinculante"
    )
    vector_repo.actualizar_payload_obra.assert_not_awaited()


@pytest.mark.asyncio
async def test_rechazar_exige_motivo():
    uc, _, _ = _uc(_obra(estado_validacion="promocion_pendiente"))

    with pytest.raises(ValueError):
        await uc.resolver(obra_id=5, aprobar=False, actor_id=20)


@pytest.mark.asyncio
async def test_el_supervisor_puede_promover_directamente_un_obrado_publicado():
    """Sin propuesta previa: el supervisor aprueba de una vez."""
    uc, obra_repo, _ = _uc(_obra())

    await uc.resolver(obra_id=5, aprobar=True, actor_id=20)

    obra_repo.promover_a_jurisprudencia.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_si_qdrant_falla_la_promocion_no_se_revierte():
    uc, obra_repo, vector_repo = _uc(_obra(estado_validacion="promocion_pendiente"))
    vector_repo.actualizar_payload_obra = AsyncMock(side_effect=RuntimeError("qdrant caido"))

    await uc.resolver(obra_id=5, aprobar=True, actor_id=20)

    obra_repo.promover_a_jurisprudencia.assert_awaited_once()
