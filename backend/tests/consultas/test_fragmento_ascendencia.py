"""Tests de FragmentoRepoImpl.get_ascendencia — CTE recursivo (Sprint 5).

Patrón Sprint 3: mock AsyncSession.execute con fixture rows.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl


def _row(**overrides) -> MagicMock:
    """Row mock con atributos accesibles por nombre (como sqlalchemy.Row)."""
    defaults = {
        "id": 1,
        "norma_id": 1,
        "obra_id": None,
        "expediente_id": None,
        "qdrant_point_id": "uuid-leaf",
        "texto": "articulo",
        "padre_ref_id": None,
        "padre_ref_key": None,
        "nivel_jerarquico": 4,
        "metadatos": {"tipo_chunk": "articulo_simple"},
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class _MockExecuteResult:
    """Mock de resultado async (session.execute) con fetchall SYNC (SQLAlchemy)."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _make_mock_execute(rows):
    """Factory: retorna función side_effect para AsyncMock.execute.

    AsyncMock al ser llamado devuelve un coroutine; side_effect evita eso
    y retorna el valor directamente (síncrono), que es lo que await espera.
    """
    result = _MockExecuteResult(rows)

    async def _execute(*args, **kwargs):
        return result

    return _execute


@pytest.mark.asyncio
async def test_get_ascendencia_jerarquia_4_niveles() -> None:
    """CTE sube 4 niveles: hoja(4) -> 3 -> 2 -> 1 (raiz). Excluye la hoja.

    Estructura:
      f1 (id=1, nivel=1) padre=None
        f2 (id=2, padre_ref_id=1, nivel=2)
          f3 (id=3, padre_ref_id=2, nivel=3)
            f4 (id=4, padre_ref_id=3, nivel=4)  <-- hoja original (excluida)
    Input: [4], max_depth=4 -> output: [f3, f2, f1] (3 ancestros)
    """
    session = MagicMock()
    execute = AsyncMock()

    rows = [
        _row(id=3, padre_ref_id=2, nivel_jerarquico=3, qdrant_point_id="uuid-p3"),
        _row(id=2, padre_ref_id=1, nivel_jerarquico=2, qdrant_point_id="uuid-p2"),
        _row(id=1, padre_ref_id=None, nivel_jerarquico=1, qdrant_point_id="uuid-p1"),
    ]
    # execute() retorna un objeto awaitable con fetchall() awaitable
    execute.side_effect = _make_mock_execute(rows)
    session.execute = execute

    repo = FragmentoRepoImpl(session)
    resultado = await repo.get_ascendencia(fragmento_ids=[4], max_depth=4)

    # 3 ancestros, hoja id=4 excluida
    assert len(resultado) == 3
    assert {f.id for f in resultado} == {1, 2, 3}
    assert all(f.nivel_jerarquico in (1, 2, 3) for f in resultado)
    # max_depth respetado (depth < max_depth en CTE)
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_ascendencia_max_depth_corta() -> None:
    """max_depth=2 corta en 2 niveles: f4 -> f3 -> f2 (depth 1,2), no llega a f1."""
    session = MagicMock()
    execute = AsyncMock()

    rows = [
        _row(id=3, padre_ref_id=2, nivel_jerarquico=3, qdrant_point_id="uuid-p3"),
        _row(id=2, padre_ref_id=1, nivel_jerarquico=2, qdrant_point_id="uuid-p2"),
    ]
    execute.side_effect = _make_mock_execute(rows)
    session.execute = execute

    repo = FragmentoRepoImpl(session)
    resultado = await repo.get_ascendencia(fragmento_ids=[4], max_depth=2)

    assert len(resultado) == 2
    assert {f.id for f in resultado} == {2, 3}
    assert all(f.nivel_jerarquico in (2, 3) for f in resultado)


@pytest.mark.asyncio
async def test_get_ascendencia_multiples_hojas() -> None:
    """Múltiples hojas comparten ancestros -> resultado deduplicado (DISTINCT)."""
    session = MagicMock()
    execute = AsyncMock()

    rows = [
        _row(id=3, padre_ref_id=2, nivel_jerarquico=3, qdrant_point_id="uuid-p3"),
        _row(id=2, padre_ref_id=1, nivel_jerarquico=2, qdrant_point_id="uuid-p2"),
        _row(id=1, padre_ref_id=None, nivel_jerarquico=1, qdrant_point_id="uuid-p1"),
    ]
    execute.side_effect = _make_mock_execute(rows)
    session.execute = execute

    repo = FragmentoRepoImpl(session)
    resultado = await repo.get_ascendencia(fragmento_ids=[4, 5], max_depth=4)

    # DISTINCT elimina duplicados (f3, f2, f1 aparecen una sola vez)
    assert len(resultado) == 3
    assert {f.id for f in resultado} == {1, 2, 3}


@pytest.mark.asyncio
async def test_get_ascendencia_lista_vacia_retorna_vacio() -> None:
    """Lista vacía -> [] sin consultar DB."""
    session = MagicMock()
    execute = AsyncMock()
    session.execute = execute

    repo = FragmentoRepoImpl(session)
    resultado = await repo.get_ascendencia(fragmento_ids=[], max_depth=3)

    assert resultado == []
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_ascendencia_id_inexistente_sin_ancestros() -> None:
    """Hoja sin padre (padre_ref_id=NULL) -> retorna [] (sin error)."""
    session = MagicMock()
    execute = AsyncMock()
    execute.return_value = _MockExecuteResult([])
    session.execute = execute

    repo = FragmentoRepoImpl(session)
    resultado = await repo.get_ascendencia(fragmento_ids=[999], max_depth=3)

    assert resultado == []
    # CTE no encuentra ancestros porque f999 no existe -> 0 rows


@pytest.mark.asyncio
async def test_asignar_padres_por_ids_ejecuta_update_batch():
    """D-S5K-01: UPDATE batch por (hijo, padre) + commit, sin SELECT."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    repo = FragmentoRepoImpl(session)

    await repo.asignar_padres_por_ids([(3, 2), (4, 2)])

    args = session.execute.await_args.args
    assert args[1] == [{"hijo": 3, "padre": 2}, {"hijo": 4, "padre": 2}]
    session.commit.assert_awaited_once()

    await repo.asignar_padres_por_ids([])
    assert session.execute.await_count == 1  # nada vacio no re-ejecuta


@pytest.mark.asyncio
async def test_get_by_qdrant_ids_excluye_soft_delete() -> None:
    """El hydrate no devuelve fragmentos de normas/obras desactivadas."""
    from unittest.mock import AsyncMock, MagicMock

    from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl

    stmts: list = []

    async def _capture(stmt):
        stmts.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_capture)
    repo = FragmentoRepoImpl(session)

    out = await repo.get_by_qdrant_ids(["q1", "q2"])

    assert out == []
    sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN" in sql.upper()
    assert "activo" in sql
