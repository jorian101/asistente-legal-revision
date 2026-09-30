"""Tests de RerankerService P5.2 — protección de recursos.

Cubre:
- Techo de candidatos: solo N van al cross-encoder.
- Timeout duro: degrada si el reranker no responde.
- Circuit breaker: 2 fallos seguidos abren el breaker (degrada sin intentar).
- Close delega al reranker.
"""

from __future__ import annotations

import asyncio

import pytest

from src.application.services.reranker_service import RerankerService
from src.domain.entities.fragmento import Fragmento


def _frag(i: int) -> Fragmento:
    return Fragmento(
        id=i,
        norma_id=1,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=f"q{i}",
        texto=f"Fragmento {i}",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


class _RerankerFake:
    """Reranker fake: registra calls y responde o lanza según config."""

    def __init__(self, delay: float = 0.0, error: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self.delay = delay
        self.error = error
        self.closed = False

    async def rerank(self, query: str, candidates: list[str], top_k: int) -> list:
        self.calls.append(candidates)
        if self.error is not None:
            raise self.error
        if self.delay:
            await asyncio.sleep(self.delay)
        return [(i, 1.0 - i * 0.01) for i in range(min(top_k, len(candidates)))]

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_techo_de_candidatos() -> None:
    """Con max_candidates=3, el fake recibe a lo sumo 3 textos."""
    fake = _RerankerFake()
    svc = RerankerService(fake, max_candidates=3, timeout=5.0)
    candidatos = [(f, 1.0) for f in [_frag(i) for i in range(10)]]

    out = await svc.aplicar("q", candidatos, top_k=2)

    assert len(fake.calls[0]) == 3  # techo aplicado
    assert len(out) == 2  # top_k


@pytest.mark.asyncio
async def test_timeout_degrada() -> None:
    """Si el reranker tarda más que el timeout, degrada a ranking fase 2."""
    fake = _RerankerFake(delay=1.0)
    svc = RerankerService(fake, max_candidates=5, timeout=0.2)
    candidatos = [(f, 1.0) for f in [_frag(i) for i in range(5)]]

    out = await svc.aplicar("q", candidatos, top_k=3)

    # Degradó sin errores, conservando el orden de fase 2 recortado a top_k.
    assert len(out) == 3
    assert [f.id for f, _ in out] == [0, 1, 2]


@pytest.mark.asyncio
async def test_circuit_breaker_abre_tras_dos_fallos() -> None:
    """Dos fallos seguidos abren el breaker; el tercero degrada sin intentar."""
    fake = _RerankerFake(error=RuntimeError("server down"))
    svc = RerankerService(fake, max_candidates=5, timeout=1.0)
    candidatos = [(f, 1.0) for f in [_frag(i) for i in range(5)]]

    await svc.aplicar("q", candidatos, top_k=3)  # fallo 1
    await svc.aplicar("q", candidatos, top_k=3)  # fallo 2 -> abre breaker
    calls_antes = len(fake.calls)
    await svc.aplicar("q", candidatos, top_k=3)  # breaker abierto

    assert len(fake.calls) == calls_antes  # no se intentó de nuevo


@pytest.mark.asyncio
async def test_fallo_aislado_no_abre_breaker() -> None:
    """Un fallo aislado no degrada la siguiente llamada si luego responde."""
    llamadas = 0

    class _Intermitente:
        async def rerank(self, query, candidates, top_k):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 1:
                raise RuntimeError("transient")
            return [(i, 1.0 - i * 0.01) for i in range(min(top_k, len(candidates)))]

    svc = RerankerService(_Intermitente(), max_candidates=5, timeout=1.0)
    candidatos = [(f, 1.0) for f in [_frag(i) for i in range(5)]]

    await svc.aplicar("q", candidatos, top_k=3)  # fallo (contador=1)
    out = await svc.aplicar("q", candidatos, top_k=3)  # éxito -> reset

    assert len(out) == 3
    assert svc._fallos_seguidos == 0  # reset por éxito


@pytest.mark.asyncio
async def test_close_cierra_reranker() -> None:
    """close() delega al reranker si existe."""
    fake = _RerankerFake()
    svc = RerankerService(fake)
    await svc.close()
    assert fake.closed


@pytest.mark.asyncio
async def test_sin_reranker_degrada() -> None:
    """Sin reranker (None): conserva orden de fase 2."""
    svc = RerankerService(None)
    candidatos = [(f, 1.0) for f in [_frag(i) for i in range(5)]]
    out = await svc.aplicar("q", candidatos, top_k=2)
    assert len(out) == 2
