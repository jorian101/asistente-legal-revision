"""Tests del adapter PostgreSQL RecomendacionRepoImpl.

Sin DB live — MagicMock session. Focus:
- recomendar: crea (estado pendiente/recomendada segun quien), upsert por par único.
- listar_por_expediente: solo aprobadas por defecto.
- aprobar: pendiente -> recomendada, con aprobado_por.
- rechazar: pendiente -> rechazada, con motivo.
- aprobar_todas: lote (con o sin ids) -> cuenta actualizada.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.recomendacion_doctrina import (
    RecomendacionDoctrinaModel,
)
from src.adapters.postgres.repos.recomendacion_repo import RecomendacionRepoImpl


def _mock_session_execute(
    scalar_or_none: RecomendacionDoctrinaModel | None = None,
    scalar_all: list[RecomendacionDoctrinaModel] | None = None,
) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.one_or_none.return_value = scalar_or_none
    if scalar_all is not None:
        scalars.all.return_value = scalar_all
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    return session


def _model(
    id_: int = 1,
    obra_global_id: int = 10,
    expediente_id: int = 7,
    recomendado_por: int = 29,
    estado: str = "pendiente",
) -> RecomendacionDoctrinaModel:
    from datetime import UTC, datetime

    return RecomendacionDoctrinaModel(
        id=id_,
        obra_global_id=obra_global_id,
        expediente_id=expediente_id,
        recomendado_por=recomendado_por,
        estado=estado,
        aprobado_por=None,
        motivo_rechazo=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_recomendar_crea_sin_par_existente() -> None:
    """Sin par único previo, crea una recomendación nueva."""
    session = _mock_session_execute(scalar_or_none=None)
    repo = RecomendacionRepoImpl(session)

    rec = await repo.recomendar(
        obra_global_id=10,
        expediente_id=7,
        recomendado_por=29,
        estado="pendiente",
    )

    assert rec.obra_global_id == 10
    assert rec.expediente_id == 7
    assert rec.estado == "pendiente"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_recomendar_upsert_si_par_existente() -> None:
    """Si el par único ya existe, actualiza estado/recomendado_por."""
    model = _model(estado="rechazada")
    session = _mock_session_execute(scalar_or_none=model)
    repo = RecomendacionRepoImpl(session)

    rec = await repo.recomendar(
        obra_global_id=10,
        expediente_id=7,
        recomendado_por=29,
        estado="pendiente",
    )

    assert rec.estado == "pendiente"
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_listar_por_expediente_filtra_aprobadas() -> None:
    """listar_por_expediente solo trae las aprobadas por defecto."""
    session = _mock_session_execute(scalar_all=[_model(estado="recomendada")])
    repo = RecomendacionRepoImpl(session)

    recs = await repo.listar_por_expediente(7)

    assert len(recs) == 1
    assert recs[0].estado == "recomendada"


@pytest.mark.asyncio
async def test_aprobar_cambia_estado_con_aprobado_por() -> None:
    model = _model(estado="pendiente")
    session = _mock_session_execute(scalar_or_none=model)
    repo = RecomendacionRepoImpl(session)

    rec = await repo.aprobar(1, aprobado_por=26)

    assert rec is not None
    assert rec.estado == "recomendada"
    assert rec.aprobado_por == 26


@pytest.mark.asyncio
async def test_aprobar_inexistente_devuelve_none() -> None:
    session = _mock_session_execute(scalar_or_none=None)
    repo = RecomendacionRepoImpl(session)

    rec = await repo.aprobar(999, aprobado_por=26)

    assert rec is None


@pytest.mark.asyncio
async def test_rechazar_cambia_estado_con_motivo() -> None:
    model = _model(estado="pendiente")
    session = _mock_session_execute(scalar_or_none=model)
    repo = RecomendacionRepoImpl(session)

    rec = await repo.rechazar(1, aprobado_por=26, motivo="no aplica")

    assert rec is not None
    assert rec.estado == "rechazada"
    assert rec.motivo_rechazo == "no aplica"


def _resultados_secuenciales(*respuestas):
    """Un result por cada session.execute sucesivo.

    Cada respuesta es (one_or_none, scalar_one_or_none).
    """
    results = []
    for one_or_none, scalar_uno in respuestas:
        result = MagicMock()
        scalars = MagicMock()
        scalars.one_or_none.return_value = one_or_none
        result.scalars.return_value = scalars
        result.scalar_one_or_none = MagicMock(return_value=scalar_uno)
        results.append(result)
    return results


@pytest.mark.asyncio
async def test_recomendar_corpus_reutiliza_fila_obra_duplicada() -> None:
    """Vía corpus con rec por obra del mismo ref -> actualiza, no duplica."""
    existente = _model(id_=3, obra_global_id=10, expediente_id=7, estado="pendiente")
    session = _mock_session_execute()
    session.execute = AsyncMock(
        side_effect=_resultados_secuenciales((None, None), (existente, None))
    )
    repo = RecomendacionRepoImpl(session)

    rec = await repo.recomendar(
        obra_global_id=None,
        expediente_id=7,
        recomendado_por=26,
        estado="recomendada",
        corpus="jurisprudencia",
        corpus_ref="SCP-0623-2024-S4",
    )

    assert rec.id == 3
    assert rec.estado == "recomendada"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_recomendar_obra_reutiliza_fila_corpus_duplicada() -> None:
    """Vía obra puntero con rec por corpus del mismo ref -> no duplica."""
    existente = _model(id_=4, obra_global_id=None, expediente_id=7, estado="pendiente")
    session = _mock_session_execute()
    session.execute = AsyncMock(
        side_effect=_resultados_secuenciales(
            (None, None), (None, "SCP-0623-2024-S4"), (existente, None)
        )
    )
    repo = RecomendacionRepoImpl(session)

    rec = await repo.recomendar(
        obra_global_id=10,
        expediente_id=7,
        recomendado_por=26,
        estado="recomendada",
    )

    assert rec.id == 4
    assert rec.estado == "recomendada"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_aprobar_todas_con_ids_vacios_no_aprueba_nada() -> None:
    """Una selección vacía (`[]`) no es "todas": no debe tocar ninguna fila."""
    session = _mock_session_execute()
    repo = RecomendacionRepoImpl(session)

    assert await repo.aprobar_todas(1, ids=[]) == 0

    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_aprobar_todas_sin_ids_aprueba_todas_las_pendientes() -> None:
    session = _mock_session_execute()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=3))
    repo = RecomendacionRepoImpl(session)

    assert await repo.aprobar_todas(1) == 3

    sql = str(session.execute.await_args.args[0]).lower()
    assert "id in" not in sql and "id in (" not in sql
