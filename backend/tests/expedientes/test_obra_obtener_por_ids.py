"""Tests de ObraRepoImpl.obtener_por_ids — batch Regla 5 (Sprint 5).

Cubre:
- Batch filtra Regla 5: propias + publicadas, excluye privadas ajenas.
- Lista vacía retorna dict vacío sin query.
- Dict keys = obra_id para lookup O(1) en EvaluadorVisibilidad.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.obra_repo import ObraRepoImpl


def _model(**overrides) -> MagicMock:
    """ObraModel mock con atributos."""
    defaults = {
        "id": 1,
        "expediente_id": 1,
        "propietario_id": 1,
        "tipo_documento": "sentencia",
        "nombre_archivo": "sentencia.pdf",
        "contenido_texto": "...",
        "ruta_archivo": None,
        "fojas_inicio": None,
        "fojas_fin": None,
        "estado_visibilidad": "privado",
        "fuente": "carga_usuario",
        "tamano_archivo": None,
        "estado_procesamiento": "completado",
        "created_at": None,
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class _MockExecuteResult:
    """Mock de resultado SQLAlchemy con scalars().all() sync."""

    def __init__(self, models):
        self._models = models

    def scalars(self):
        class _Scalars:
            def __init__(self, models):
                self._models = models

            def all(self):
                return self._models

        return _Scalars(self._models)


def _make_mock_execute(models, usuario_id):
    """Factory: mock que FILTRA modelos según Regla 5 (propias + publicadas)."""
    # Simular el WHERE del SQL: id IN :ids AND (propietario_id = :uid OR publicado)
    filtered = [
        m for m in models if m.propietario_id == usuario_id or m.estado_visibilidad == "publicado"
    ]
    result = _MockExecuteResult(filtered)

    async def _execute(*args, **kwargs):
        return result

    return _execute


@pytest.mark.asyncio
async def test_obtener_por_ids_batch_regla5_solo_propias_y_publicadas() -> None:
    """4 obras mixtas -> dict solo retiene propias + publicadas.

    usuario_id=1:
    - obra 10: propia privada -> INCLUYE
    - obra 20: propia publicada -> INCLUYE
    - obra 30: ajena privada -> EXCLUYE
    - obra 40: ajena publicada -> INCLUYE
    """
    session = MagicMock()
    execute = AsyncMock()

    models = [
        _model(id=10, propietario_id=1, estado_visibilidad="privado"),
        _model(id=20, propietario_id=1, estado_visibilidad="publicado"),
        _model(id=30, propietario_id=2, estado_visibilidad="privado"),
        _model(id=40, propietario_id=2, estado_visibilidad="publicado"),
    ]
    execute.side_effect = _make_mock_execute(models, usuario_id=1)
    session.execute = execute

    repo = ObraRepoImpl(session)
    resultado = await repo.obtener_por_ids(obra_ids=[10, 20, 30, 40], usuario_id=1)

    assert len(resultado) == 3
    assert set(resultado.keys()) == {10, 20, 40}
    assert 30 not in resultado, "Obra privada ajena (id=30) debe ser excluida"


@pytest.mark.asyncio
async def test_obtener_por_ids_lista_vacia_retorna_dict_vacio() -> None:
    """Lista vacía -> {} sin consultar DB."""
    session = MagicMock()
    execute = AsyncMock()
    session.execute = execute

    repo = ObraRepoImpl(session)
    resultado = await repo.obtener_por_ids(obra_ids=[], usuario_id=1)

    assert resultado == {}
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_obtener_por_ids_solo_una_propia() -> None:
    """Una sola obra propia -> dict con 1 entrada."""
    session = MagicMock()
    execute = AsyncMock()

    execute.side_effect = _make_mock_execute(
        [
            _model(id=5, propietario_id=1, estado_visibilidad="privado"),
        ],
        usuario_id=1,
    )
    session.execute = execute

    repo = ObraRepoImpl(session)
    resultado = await repo.obtener_por_ids(obra_ids=[5], usuario_id=1)

    assert resultado == {5: resultado[5]}
    assert resultado[5].propietario_id == 1


@pytest.mark.asyncio
async def test_obtener_por_ids_todas_publicadas_ajenas_incluidas() -> None:
    """Obras todas publicadas de otros usuarios -> todas incluidas."""
    session = MagicMock()
    execute = AsyncMock()

    models = [
        _model(id=100, propietario_id=2, estado_visibilidad="publicado"),
        _model(id=200, propietario_id=3, estado_visibilidad="publicado"),
    ]
    execute.side_effect = _make_mock_execute(models, usuario_id=1)
    session.execute = execute

    repo = ObraRepoImpl(session)
    resultado = await repo.obtener_por_ids(obra_ids=[100, 200], usuario_id=1)

    assert len(resultado) == 2
    assert set(resultado.keys()) == {100, 200}
    assert all(r.estado_visibilidad == "publicado" for r in resultado.values())


@pytest.mark.asyncio
async def test_obtener_por_ids_duplicados_en_lista_deduplica() -> None:
    """IDs duplicados en input -> SQL IN los deduplica, dict keys únicos."""
    session = MagicMock()
    execute = AsyncMock()

    execute.side_effect = _make_mock_execute(
        [
            _model(id=7, propietario_id=1, estado_visibilidad="privado"),
        ],
        usuario_id=1,
    )
    session.execute = execute

    repo = ObraRepoImpl(session)
    resultado = await repo.obtener_por_ids(obra_ids=[7, 7, 7], usuario_id=1)

    assert len(resultado) == 1
    assert 7 in resultado
