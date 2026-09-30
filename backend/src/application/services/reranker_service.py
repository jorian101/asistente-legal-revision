"""Servicio: RerankerService — Fase 3 del pipeline RAG (Sprint 3 + P5.2).

Envoltorio del port Reranker: toma los candidatos de HybridSearcher, llama
al cross-encoder, retorna los top_k fragmentos con sus nuevos scores
(reordenados por relevancia rerankeada).

P5.2 — Protección de recursos (evitar congelar la laptop):
- `max_candidates`: techo de documentos que se envían al cross-encoder.
  Si el corpus entrega más candidatos, se recortan a los N con mejor score
  de fase 2 (el CrossEncoder es el cuello de botella de CPU/RAM).
- `timeout`: duro (asyncio.wait_for) sobre la llamada al reranker. Si el
  servidor no responde a tiempo, se degrada a ranking de fase 2.
- Circuit breaker: tras `fallos_consecutivos` errores seguidos se degrada
  durante `ventana_cooldown_s` (evita martillar un servidor colgado).

Si el port `Reranker` es `None`, degrada: retorna los candidatos sin rerank,
preservando el orden por score de HybridSearcher.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from src.domain.entities.fragmento import Fragmento

if TYPE_CHECKING:
    from src.application.ports.reranker import Reranker


logger = logging.getLogger(__name__)


class RerankerService:
    """Fase 3 del pipeline: reranking de candidatos por cross-encoder."""

    def __init__(
        self,
        reranker: Reranker | None,
        *,
        max_candidates: int = 15,
        timeout: float = 45.0,
        fallos_consecutivos: int = 2,
        ventana_cooldown_s: float = 60.0,
    ) -> None:
        self._reranker = reranker
        self._max_candidates = max_candidates
        self._timeout = timeout
        self._fallos_consecutivos = fallos_consecutivos
        self._ventana_cooldown_s = ventana_cooldown_s
        self._fallos_seguidos = 0
        self._hasta: float = 0.0  # timestamp monotónico hasta el que degradar

    def _en_cooldown(self) -> bool:
        """True si el circuit breaker está abierto (degradar)."""
        return self._fallos_seguidos >= self._fallos_consecutivos and time.monotonic() < self._hasta

    def _abrir_cooldown(self) -> None:
        self._hasta = time.monotonic() + self._ventana_cooldown_s

    async def _rerank_con_timeout(self, query: str, textos: list[str], top_k: int):
        """Ejecuta el rerank con timeout duro; devuelve ranked o [] si timeout."""
        return await asyncio.wait_for(
            self._reranker.rerank(query=query, candidates=textos, top_k=top_k),
            timeout=self._timeout,
        )

    async def aplicar(
        self,
        query: str,
        candidatos: list[tuple[Fragmento, float]],
        top_k: int,
    ) -> list[tuple[Fragmento, float]]:
        """Rerankea candidatos y retorna top_k fragmentos con score rerankeado.

        Protecciones P5.2: techo de candidatos, timeout duro y circuit breaker.
        Cualquier fallo degrada a ranking de fase 2 (nunca rompe el pipeline).

        Args:
            query: Texto de la consulta original.
            candidatos: Lista de (Fragmento, score_inicial) de HybridSearcher.
            top_k: Numero maximo de fragmentos a retornar.

        Returns:
            Lista de (Fragmento, score) ordenada desc por score.
        """
        if not candidatos:
            return []

        if self._reranker is None:
            logger.warning(
                "RerankerService: reranker no configurado. Omitiendo fase 3 — "
                "resultados sin re-ranking de precision."
            )
            return candidatos[:top_k]

        if self._en_cooldown():
            logger.warning(
                "RerankerService: circuit breaker abierto (%d fallos). "
                "Degradando a ranking de fase 2 hasta %.0fs.",
                self._fallos_seguidos,
                self._hasta - time.monotonic(),
            )
            return candidatos[:top_k]

        # Techo de candidatos: el CrossEncoder es el cuello de botella.
        candidatos_recortados = candidatos[: self._max_candidates]
        textos = [frag.texto for frag, _ in candidatos_recortados]

        try:
            ranked = await self._rerank_con_timeout(query, textos, top_k)
        except (TimeoutError, Exception) as exc:
            self._fallos_seguidos += 1
            if self._fallos_seguidos >= self._fallos_consecutivos:
                self._abrir_cooldown()
            logger.warning(
                "RerankerService: fallo en rerank (%s). Fallos seguidos=%d. "
                "Degradando a ranking de fase 2. Detalle: %s",
                type(exc).__name__,
                self._fallos_seguidos,
                exc,
            )
            return candidatos[:top_k]

        # Éxito: reset del contador.
        self._fallos_seguidos = 0

        resultado: list[tuple[Fragmento, float]] = []
        for idx_original, nuevo_score in ranked:
            fragmento = candidatos_recortados[idx_original][0]
            resultado.append((fragmento, nuevo_score))
        return resultado

    async def close(self) -> None:
        """Cierra el cliente HTTP del reranker si aplica."""
        if self._reranker is not None and hasattr(self._reranker, "close"):
            await self._reranker.close()
