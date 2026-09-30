"""Tests del RerankerService (Fase 3 del pipeline RAG).

Cubre:
- RerankerService aplica Reranker port con los textos correctos.
- Resultado se ordena desc por score rerankeado.
- Top_k se trunca.
- Candidatos vacios devuelve [].
- Preserva identidad de Fragmentos (no los clona).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.reranker_service import RerankerService
from src.domain.entities.fragmento import Fragmento


def _frag(qid: str, texto: str) -> Fragmento:
    return Fragmento(
        id=None,
        norma_id=1,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=qid,
        texto=texto,
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


def _make_service(reranked: list[tuple[int, float]]) -> RerankerService:
    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=reranked)
    return RerankerService(reranker=reranker)


@pytest.mark.asyncio
async def test_reranker_service_ordena_por_score_desc() -> None:
    """El servicio preserva el orden desc del Reranker port."""
    f1 = _frag("a", "texto A")
    f2 = _frag("b", "texto B")
    f3 = _frag("c", "texto C")
    candidatos = [(f1, 0.5), (f2, 0.9), (f3, 0.7)]

    # El reranker retorna los indices en orden desc por nuevo score.
    svc = _make_service([(2, 0.95), (0, 0.71), (1, 0.12)])

    out = await svc.aplicar(query="q", candidatos=candidatos, top_k=3)

    assert [f.qdrant_point_id for f, _ in out] == ["c", "a", "b"]
    assert [s for _, s in out] == [0.95, 0.71, 0.12]


@pytest.mark.asyncio
async def test_reranker_service_trunca_via_port() -> None:
    """El port Reranker (HttpReranker) ya trunca a top_k; el servicio respeta eso.

    Verifica que cuando el port devuelve menos de lo que se le envio, el
    servicio devuelve esa misma cantidad (la responsabilidad de truncado
    vive en el port, no en el servicio).
    """
    candidatos = [(_frag(str(i), f"texto {i}"), 1.0) for i in range(5)]
    # Port mock devuelve solo 2 (ya truncado).
    svc = _make_service([(0, 0.9), (2, 0.5)])

    out = await svc.aplicar(query="q", candidatos=candidatos, top_k=2)

    assert len(out) == 2


@pytest.mark.asyncio
async def test_reranker_service_pasa_textos_correctos() -> None:
    """El servicio pasa al Reranker solo los textos (no entidades).

    Tambien verifica que el port Reranker ya trunca a top_k internamente
    (HttpReranker.rerank hace ranked[:top_k]). El servicio no vuelve
    a truncar (delega responsabilidad al port).
    """
    f1 = _frag("a", "Articulo 1 sobre desobediencia.")
    f2 = _frag("b", "Articulo 2 sobre insubordinacion.")
    # El port (mock) simula que YA devolvio truncado a 2.
    svc = _make_service([(0, 0.9), (1, 0.1)])

    out = await svc.aplicar(query="desobediencia", candidatos=[(f1, 0.0), (f2, 0.0)], top_k=2)

    call = svc._reranker.rerank.await_args
    assert call is not None
    assert call.kwargs["query"] == "desobediencia"
    assert call.kwargs["candidates"] == [
        "Articulo 1 sobre desobediencia.",
        "Articulo 2 sobre insubordinacion.",
    ]
    assert call.kwargs["top_k"] == 2
    assert len(out) == 2


@pytest.mark.asyncio
async def test_reranker_service_candidatos_vacios_devuelve_empty() -> None:
    """Sin candidatos no se llama al Reranker y se devuelve []."""
    svc = _make_service([])

    out = await svc.aplicar(query="q", candidatos=[], top_k=5)

    assert out == []
    svc._reranker.rerank.assert_not_called()


@pytest.mark.asyncio
async def test_reranker_service_preserva_identidad_frag() -> None:
    """El servicio NO clona Fragmentos — mantiene la misma instancia."""
    f1 = _frag("a", "X")
    f2 = _frag("b", "Y")
    svc = _make_service([(1, 0.5), (0, 0.4)])

    out = await svc.aplicar(query="q", candidatos=[(f1, 0.0), (f2, 0.0)], top_k=2)

    assert out[0][0] is f2
    assert out[1][0] is f1


@pytest.mark.asyncio
async def test_reranker_service_sin_reranker_degrada_a_orden_score() -> None:
    """Si el port Reranker es None (reranker no configurado en .env),
    RerankerService retorna candidatos recortados a top_k preservando
    el orden por score de la fase 2 (HybridSearcher). No llama al port.

    Regresion: el boot del backend NO debe depender de servicios externos
    (LLM/reranker); si no hay reranker configurado, el pipeline degrada
    con calidad reducida en vez de fallar.
    """
    f1 = _frag("a", "X")
    f2 = _frag("b", "Y")
    f3 = _frag("c", "Z")
    svc = RerankerService(reranker=None)

    out = await svc.aplicar(
        query="q",
        candidatos=[(f1, 0.9), (f2, 0.7), (f3, 0.5)],
        top_k=2,
    )

    # Preserva orden por score (ya viene desc) y trunca a top_k.
    assert len(out) == 2
    assert out[0] == (f1, 0.9)
    assert out[1] == (f2, 0.7)


@pytest.mark.asyncio
async def test_reranker_service_sin_reranker_candidatos_vacios_devuelve_empty() -> None:
    """Con port None y sin candidatos, devuelve [] sin errores."""
    svc = RerankerService(reranker=None)

    out = await svc.aplicar(query="q", candidatos=[], top_k=5)

    assert out == []
