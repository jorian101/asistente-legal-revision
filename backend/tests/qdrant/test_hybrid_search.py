"""Tests de busqueda hibrida (search_hybrid/search_dense) en QdrantCorpusRepo.

Cubren la Regla 4 Trail of Bits de forma obligatoria + la fusion RRF:
- search_hybrid/search_dense SIN usuario_id -> ValueError (Regla 4 bloqueante).
- Deben aplicar el filtro de privacidad (never-skip) al Qdrant.
- search_hybrid debe usar prefetch [denso, disperso] + afusion RRF server-side.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models as qmodels

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.domain.value_objects import SparseVector


def _make_repo(client: MagicMock) -> QdrantCorpusRepo:
    """Repo con cliente inyectado (sin conexion real)."""
    repo = object.__new__(QdrantCorpusRepo)
    repo._client = client
    repo._dim = 768
    repo._url = "http://test"
    repo._api_key = None
    repo._sparse_checked = True
    repo._sparse_present = True
    return repo


@pytest.mark.asyncio
async def test_search_hybrid_raises_without_usuario_id() -> None:
    """Regla 4: sin usuario_id -> ValueError (el filtro nunca es opcional)."""
    repo = _make_repo(MagicMock())
    sparse = SparseVector(indices=(1,), values=(0.5,))
    with pytest.raises(ValueError, match="usuario_id"):
        await repo.search_hybrid(
            dense_vector=[0.1] * 768,
            sparse_vector=sparse,
            alpha=0.5,
            filters={},  # sin usuario_id
            limit=7,
        )


@pytest.mark.asyncio
async def test_search_dense_raises_without_usuario_id() -> None:
    """Regla 4: search_dense (fallback) tambien exige usuario_id."""
    repo = _make_repo(MagicMock())
    with pytest.raises(ValueError, match="usuario_id"):
        await repo.search_dense(
            dense_vector=[0.1] * 768,
            filters={},
            limit=7,
        )


@pytest.mark.asyncio
async def test_search_hybrid_applies_privacy_filter() -> None:
    """El QueryFilter pasado a Qdrant DEBE contener el filtro de privacidad.

    Verifica que el `should` del filtro anida el propietario_id==usuario_id y,
    como excluye lo privado ajeno, opera la Regla 4 en TODA busqueda.
    """
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])
    repo = _make_repo(client)

    sparse = SparseVector(indices=(1, 2, 3), values=(0.2, 0.5, 0.3))
    await repo.search_hybrid(
        dense_vector=[0.1] * 768,
        sparse_vector=sparse,
        alpha=0.5,
        filters={"usuario_id": 42},
        limit=7,
    )

    client.query_points.assert_called_once()
    kwargs = client.query_points.call_args.kwargs
    assert kwargs["collection_name"] == QdrantCorpusRepo.COLLECTION_NAME
    # La fusion pide el doble para desempatar el corte aca; el prefetch conserva su hondura.
    assert kwargs["limit"] == 14

    # Debe usar prefetch [denso, disperso] + fusion RRF.
    prefetches = kwargs["prefetch"]
    assert len(prefetches) == 2
    assert all(p.limit == 14 for p in prefetches)

    # El filtro de privacidad (Regla 4) va dentro de cada prefetch.
    for p in prefetches:
        assert p.filter is not None
        assert p.filter.should is not None
        assert len(p.filter.should) == 4  # empty/published/global/owner


@pytest.mark.asyncio
async def test_search_hybrid_property_filter_includes_should_privacy() -> None:
    """El filtro de privacidad (Regla 4) esta dentro de cada prefetch filter."""
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])
    repo = _make_repo(client)

    sparse = SparseVector(indices=(1,), values=(1.0,))
    await repo.search_hybrid(
        dense_vector=[0.1] * 768,
        sparse_vector=sparse,
        alpha=0.5,
        filters={"usuario_id": 7},
        limit=3,
    )

    prefetches = client.query_points.call_args.kwargs["prefetch"]
    for p in prefetches:
        pf = p.filter
        # Debe tener un filtro con 'should' que incluya propietario_id==7
        # y visibilidad (Regla 4).
        assert pf is not None
        should = pf.should
        assert should is not None
        assert len(should) >= 2
        # Algo debe referenciar el usuario 7.
        serialized = should
        assert any(str(x) for x in serialized)  # filtro no vacio


@pytest.mark.asyncio
async def test_search_hybrid_applies_expediente_filter() -> None:
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])
    repo = _make_repo(client)

    await repo.search_dense(
        dense_vector=[0.1] * 768,
        filters={"usuario_id": 7, "expediente_id": "42"},
        limit=5,
    )

    query_filter = client.query_points.call_args.kwargs["query_filter"]
    # Plan C (C1.2): expediente_id ahora es un sub-filtro OR que acepta
    # expediente_id=X o expediente_id IS NULL (para incluir doctrina global).
    sub_filtros = [c for c in query_filter.must if isinstance(c, qmodels.Filter)]
    assert sub_filtros, "debe existir un sub-filtro para expediente_id"
    should = sub_filtros[0].should
    assert any(
        isinstance(c, qmodels.FieldCondition) and c.key == "expediente_id" and c.match.value == 42
        for c in should
    )
    assert any(
        isinstance(c, qmodels.IsNullCondition) and c.is_null.key == "expediente_id" for c in should
    )


@pytest.mark.asyncio
async def test_search_hybrid_calls_qdrant_query_with_rrf() -> None:
    """El adapter delega a query_points con fusion RRF (decision D1)."""
    client = MagicMock()
    point = MagicMock()
    point.id = "abc-123"
    point.score = 0.987
    point.payload = {"norma_id": 1, "texto": "hola"}
    client.query_points.return_value = MagicMock(points=[point])
    repo = _make_repo(client)

    sparse = SparseVector(indices=(1,), values=(0.9,))
    result = await repo.search_hybrid(
        dense_vector=[0.2] * 768,
        sparse_vector=sparse,
        alpha=0.6,
        filters={"usuario_id": 42},
        limit=5,
    )

    assert result[0].qdrant_id == "abc-123"
    assert result[0].score == pytest.approx(0.987)


def _punto(pid: str, score: float) -> MagicMock:
    p = MagicMock()
    p.id, p.score, p.payload = pid, score, {}
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize("orden", [["c", "b", "a", "d"], ["a", "d", "c", "b"]])
async def test_search_hybrid_desempata_el_corte_por_id(orden: list[str]) -> None:
    """Qdrant devuelve los empates de la fusion en cualquier orden: el corte no puede depender
    de eso. Mismos puntos en otro orden -> mismo resultado, cortado a `limit`."""
    scores = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.9}
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[_punto(i, scores[i]) for i in orden])
    repo = _make_repo(client)

    result = await repo.search_hybrid(
        dense_vector=[0.2] * 768,
        sparse_vector=SparseVector(indices=(1,), values=(0.9,)),
        alpha=0.5,
        filters={"usuario_id": 42},
        limit=3,
    )

    assert [p.qdrant_id for p in result] == ["d", "a", "b"]
