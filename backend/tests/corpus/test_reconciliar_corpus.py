"""Tests unitarios de ReconciliarCorpus (Regla 3 offline).

Mockean los ports (FragmentoRepo, CorpusRepoVectorial). Sin I/O real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.reconciliar_corpus import ReconciliacionResult, ReconciliarCorpus


@pytest.mark.asyncio
async def test_reconciliacion_sin_huerfanos():
    f_repo = MagicMock()
    f_repo.list_all_qdrant_ids = AsyncMock(return_value=["a1", "a2", "a3"])
    v_repo = MagicMock()
    v_repo.list_all_ids = AsyncMock(return_value=["a1", "a2", "a3"])
    v_repo.delete_many = AsyncMock()

    uc = ReconciliarCorpus(f_repo, v_repo)
    result = await uc.ejecutar()

    assert isinstance(result, ReconciliacionResult)
    assert result.pg_count == 3
    assert result.qdrant_count == 3
    assert result.huerfanos_eliminados == 0
    v_repo.delete_many.assert_not_called()


@pytest.mark.asyncio
async def test_reconciliacion_con_huerfanos():
    f_repo = MagicMock()
    f_repo.list_all_qdrant_ids = AsyncMock(return_value=["a1", "a2"])
    v_repo = MagicMock()
    v_repo.list_all_ids = AsyncMock(return_value=["a1", "a2", "b1", "b2"])
    v_repo.delete_many = AsyncMock()

    uc = ReconciliarCorpus(f_repo, v_repo)
    result = await uc.ejecutar()

    assert result.pg_count == 2
    assert result.qdrant_count == 4
    assert result.huerfanos_eliminados == 2
    v_repo.delete_many.assert_called_once()
    ids_borrados = set(v_repo.delete_many.call_args[0][0])
    assert ids_borrados == {"b1", "b2"}


@pytest.mark.asyncio
async def test_reconciliacion_bd_vacia():
    f_repo = MagicMock()
    f_repo.list_all_qdrant_ids = AsyncMock(return_value=[])
    v_repo = MagicMock()
    v_repo.list_all_ids = AsyncMock(return_value=["a1"])
    v_repo.delete_many = AsyncMock()

    uc = ReconciliarCorpus(f_repo, v_repo)
    result = await uc.ejecutar()

    assert result.pg_count == 0
    assert result.qdrant_count == 1
    assert result.huerfanos_eliminados == 1


@pytest.mark.asyncio
async def test_reconciliacion_qdrant_vacio():
    f_repo = MagicMock()
    f_repo.list_all_qdrant_ids = AsyncMock(return_value=["a1", "a2"])
    v_repo = MagicMock()
    v_repo.list_all_ids = AsyncMock(return_value=[])
    v_repo.delete_many = AsyncMock()

    uc = ReconciliarCorpus(f_repo, v_repo)
    result = await uc.ejecutar()

    assert result.pg_count == 2
    assert result.qdrant_count == 0
    assert result.huerfanos_eliminados == 0


@pytest.mark.asyncio
async def test_reconciliacion_tres_colecciones():
    """N1/N2/N3: huérfanos por colección, conteos agregados."""
    f_repo = MagicMock()
    f_repo.list_all_qdrant_ids = AsyncMock(return_value=["a1", "j1", "d1"])

    def _v_repo(ids):
        v = MagicMock()
        v.list_all_ids = AsyncMock(return_value=ids)
        v.delete_many = AsyncMock()
        return v

    v_main = _v_repo(["a1", "x1"])
    v_juris = _v_repo(["j1"])
    v_doc = _v_repo(["d1", "y1", "y2"])

    uc = ReconciliarCorpus(f_repo, [v_main, v_juris, v_doc])
    result = await uc.ejecutar()

    assert result.pg_count == 3
    assert result.qdrant_count == 6
    assert result.huerfanos_eliminados == 3
    v_main.delete_many.assert_awaited_once_with(["x1"])
    v_juris.delete_many.assert_not_called()
    assert sorted(v_doc.delete_many.await_args.args[0]) == ["y1", "y2"]
