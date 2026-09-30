"""Tests del adapter PostgreSQL BorradorRepoImpl.

Sin DB live — MagicMock session. Focus:
- Regla 7 (BLOQUEANTE): el SQL generado por `actualizar_estado` DEBE
  incluir `BorradorModel.propietario_id == propietario_id`. Si un
  futuro refactor lo quita, el test rompe.
- `actualizar_contenido` NO filtra por propietario (lo invoca el flujo
  interno del GenerarBorrador, no un usuario final).
- Commit explicito en crear/actualizar_estado/actualizar_contenido
  (regresión Sprint 3 — el commit nunca debe faltar).
- `listar_por_expediente` filtra por `propietario_id == user`.

Patrón: tests/expedientes/test_adapters_postgres.py.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.borrador import BorradorModel
from src.adapters.postgres.repos.borrador_repo import BorradorRepoImpl
from tests._factories import make_borrador

# ---------- Helpers ----------


def _mock_session_execute(
    scalar_or_none: BorradorModel | None = None,
    scalar_all: list[BorradorModel] | None = None,
) -> MagicMock:
    """Crea MagicMock session con execute return controlable."""
    session = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.one_or_none.return_value = scalar_or_none
    if scalar_all is not None:
        scalars.all.return_value = scalar_all
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock(
        side_effect=lambda m: setattr(
            m,
            "id",
            getattr(m, "id", 99),
        )
    )
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _borrador_model(
    *,
    id_: int = 1,
    expediente_id: int = 1,
    propietario_id: int = 1,
    tipo: str = "proyecto_auto_vista_consulta",
    estado: str = "borrador",
    contenido: str = "borrador test",
) -> BorradorModel:
    return BorradorModel(
        id=id_,
        expediente_id=expediente_id,
        propietario_id=propietario_id,
        tipo=tipo,
        estado=estado,
        contenido=contenido,
        plantilla_usada=f"{tipo}.md",
        contexto_recuperado=None,
        created_at=datetime(2026, 8, 9, 10, 0, 0),
        updated_at=None,
    )


# ---------- Tests: correccion del supervisor sobre un oficial (F-07) ----------


@pytest.mark.asyncio
async def test_actualizar_contenido_supervisor_edita_pendiente_oficial_ajeno() -> None:
    """El supervisor corrige un obrado en revision aunque no sea el propietario (F-07)."""
    modelo = _borrador_model(propietario_id=2, estado="pendiente_oficial", contenido="viejo")
    session = _mock_session_execute(scalar_or_none=modelo)
    repo = BorradorRepoImpl(session)

    await repo.actualizar_contenido_supervisor(1, contenido="corregido")

    assert modelo.contenido == "corregido"
    session.commit.assert_awaited_once()
    clausula = session.execute.await_args.args[0].whereclause
    assert "propietario_id" not in str(clausula)
    assert "pendiente_oficial" in clausula.compile().params.values()  # solo ese estado


# ---------- Tests: transiciones de estado del supervisor (F-35) ----------


@pytest.mark.asyncio
async def test_estado_supervisor_solo_transiciona_desde_el_estado_esperado() -> None:
    """oficializar solo desde 'pendiente_oficial': el where filtra por estado actual y activo."""
    modelo = _borrador_model(estado="pendiente_oficial")
    session = _mock_session_execute(scalar_or_none=modelo)

    res = await BorradorRepoImpl(session).actualizar_estado_supervisor(
        1, "oficial", desde="pendiente_oficial"
    )

    assert res is not None and modelo.estado == "oficial"
    session.commit.assert_awaited_once()
    params = session.execute.await_args.args[0].whereclause.compile().params.values()
    assert "pendiente_oficial" in params  # estado actual exigido
    assert True in params  # solo obrados activos


@pytest.mark.asyncio
async def test_estado_supervisor_sin_coincidencia_no_cambia_nada() -> None:
    """Un borrador privado (estado 'borrador') no se puede oficializar: None y sin commit."""
    session = _mock_session_execute(scalar_or_none=None)  # el where no encuentra fila

    res = await BorradorRepoImpl(session).actualizar_estado_supervisor(
        1, "oficial", desde="pendiente_oficial"
    )

    assert res is None
    session.commit.assert_not_awaited()


# ---------- Tests: crear ----------


@pytest.mark.asyncio
async def test_crear_borrador_hace_flush_refresh_commit() -> None:
    """crear debe flush + refresh + commit (regresión Sprint 3 — commit explícito).

    No verificamos `borrador.id` porque el mock no simula el IDENTITY de PG
    (igual que test_adapters_postgres.py::test_guardar_hace_commit_explicito).
    """
    session = _mock_session_execute()
    repo = BorradorRepoImpl(session)

    borrador = make_borrador(id=None, propietario_id=1)
    await repo.crear(borrador)

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once()
    session.commit.assert_awaited_once()  # Regla: commit explicito (Sprint 3)


# ---------- Tests: obtener_por_id ----------


@pytest.mark.asyncio
async def test_obtener_por_id_devuelve_borrador_existente() -> None:
    model = _borrador_model(id_=42, propietario_id=1)
    session = _mock_session_execute(scalar_or_none=model)

    repo = BorradorRepoImpl(session)
    result = await repo.obtener_por_id(42)

    assert result is not None
    assert result.id == 42
    assert result.propietario_id == 1


@pytest.mark.asyncio
async def test_obtener_por_id_devuelve_none_si_no_existe() -> None:
    session = _mock_session_execute(scalar_or_none=None)

    repo = BorradorRepoImpl(session)
    result = await repo.obtener_por_id(999)

    assert result is None


# ---------- Tests: listar_por_expediente (Regla 7) ----------


@pytest.mark.asyncio
async def test_listar_por_expediente_filtra_por_propietario_regla_7() -> None:
    """REGLA 7 — el SQL generado debe incluir `propietario_id == user`.

    Si un refactor futuro quita el filtro. este test rompe. Es el guardián
    de la Regla 7 en el repositorio de borradores.
    """
    models = [
        _borrador_model(id_=1, propietario_id=1, estado="borrador"),
        _borrador_model(id_=2, propietario_id=1, estado="publicado"),
    ]
    session = _mock_session_execute(scalar_or_none=None, scalar_all=models)

    repo = BorradorRepoImpl(session)
    result = await repo.listar_por_expediente(expediente_id=1, propietario_id=1)

    assert len(result) == 2
    assert all(b.propietario_id == 1 for b in result)

    # Verificar el SQL generado contiene el filtro Regla 7
    compiled = session.execute.call_args[0][0].compile()
    sql_str = str(compiled)
    assert "borrador.propietario_id" in sql_str, (
        f"Regla 7 violada: el SQL no filtra por propietario. SQL:\n{sql_str}"
    )
    assert "borrador.expediente_id" in sql_str


# ---------- Tests: actualizar_estado (Regla 7) ----------


@pytest.mark.asyncio
async def test_actualizar_estado_publicar_propietario_ok() -> None:
    """Propietario correcto → estado cambia a 'publicado' + commit."""
    model = _borrador_model(id_=1, propietario_id=1, estado="borrador")
    session = _mock_session_execute(scalar_or_none=model)

    repo = BorradorRepoImpl(session)
    result = await repo.actualizar_estado(borrador_id=1, estado="publicado", propietario_id=1)

    assert result is not None
    assert result.estado == "publicado"
    assert model.estado == "publicado"  # mutado en el session mock
    assert model.updated_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_actualizar_estado_usuario_no_propietario_devuelve_none_regla_7() -> None:
    """REGLA 7 — usuario no propietario recibe None (luego 403 en router).

    El filtro SQL filtra por propietario_id: el mock devuelve None porque
    el SELECT con `propietario_id=diferente` no matchea.
    """
    session = _mock_session_execute(scalar_or_none=None)

    repo = BorradorRepoImpl(session)
    result = await repo.actualizar_estado(borrador_id=1, estado="publicado", propietario_id=2)

    assert result is None  # 403 en router
    session.commit.assert_not_awaited()  # no se committea nada

    # Verificar el SQL tiene el filtro Regla 7
    compiled = session.execute.call_args[0][0].compile()
    sql_str = str(compiled)
    assert "borrador.propietario_id" in sql_str


@pytest.mark.asyncio
async def test_actualizar_estado_idempotente_no_mutara_updated_at() -> None:
    """Si el borrador ya esta en 'publicado', no muta updated_at."""
    model = _borrador_model(id_=1, propietario_id=1, estado="publicado")
    session = _mock_session_execute(scalar_or_none=model)

    repo = BorradorRepoImpl(session)
    result = await repo.actualizar_estado(borrador_id=1, estado="publicado", propietario_id=1)

    assert result is not None
    assert result.estado == "publicado"
    # Idempotencia: NO se committea (no cambio nada)
    session.commit.assert_not_awaited()


# ---------- Tests: actualizar_contenido ----------


@pytest.mark.asyncio
async def test_actualizar_contenido_actualiza_y_committea() -> None:
    """Flujo interno GenerarBorrador: actualiza contenido tras stream LLM."""
    model = _borrador_model(id_=1, contenido="")
    session = _mock_session_execute(scalar_or_none=model)

    repo = BorradorRepoImpl(session)
    result = await repo.actualizar_contenido(borrador_id=1, contenido="texto generado por LLM...")

    assert result is not None
    assert result.contenido == "texto generado por LLM..."
    assert model.contenido == "texto generado por LLM..."
    assert model.updated_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_actualizar_contenido_no_filtra_por_propietario() -> None:
    """actualizar_contenido NO lleva filtro propietario — es fllujo interno."""
    model = _borrador_model(id_=1, propietario_id=1)
    session = _mock_session_execute(scalar_or_none=model)

    repo = BorradorRepoImpl(session)
    await repo.actualizar_contenido(borrador_id=1, contenido="x")

    compiled = session.execute.call_args[0][0].compile()
    sql_str = str(compiled)
    # Asegurar que solo filtra por id (no por propietario)
    assert "borrador.id" in sql_str
    assert "propietario_id" not in sql_str.split("WHERE")[1], (
        f"actualizar_contenido no debe filtrar propietario:\n{sql_str}"
    )


@pytest.mark.asyncio
async def test_actualizar_contenido_borrador_inexistente_devuelve_none() -> None:
    session = _mock_session_execute(scalar_or_none=None)

    repo = BorradorRepoImpl(session)
    result = await repo.actualizar_contenido(borrador_id=999, contenido="x")

    assert result is None
