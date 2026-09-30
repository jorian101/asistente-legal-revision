"""RerankerWithFallback — wrapper que itera endpoints ante errores transitorios.

Decision F4: si el endpoint activo falla con error transitorio (5xx, timeout,
network), el wrapper intenta el siguiente endpoint de la lista. Errores 4xx
(validacion del cliente) se propagan inmediatamente: no tienen sentido
reintentar porque el mismo request fallaria igual.

El wrapper implementa el protocolo Reranker, transparente para el
RerankerService: get_reranker() puede devolver RerankerWithFallback o un
reranker directo, el consumer no distingue.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import httpx

from src.application.ports.reranker import Reranker

logger = logging.getLogger(__name__)

# Errores que consideramos transitorios: tiene sentido reintentar con
# otro endpoint porque el fallo no es del request sino del servidor/network.
_TRANSIENT_EXC = (httpx.TimeoutException, httpx.NetworkError)

# Regex para extraer codigo HTTP de RuntimeError envuelto por adapters
# Formato tipico: "Reranker rechazo el rerank: HTTP 503 - ..."
_HTTP_STATUS_RE = re.compile(r"HTTP\s+(\d{3})")


def _extract_http_status(exc: Exception) -> int | None:
    """Extrae codigo HTTP de RuntimeError con formato '... HTTP XXX - ...'."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    if isinstance(exc, RuntimeError):
        m = _HTTP_STATUS_RE.search(str(exc))
        if m:
            return int(m.group(1))
    return None


def _is_transient_http_status(status: int) -> bool:
    """5xx = transitorio (server error). 4xx = no transitorio (client error)."""
    return status >= 500


class RerankerWithFallback:
    """Reranker que prueba endpoints en orden y cae al siguiente ante transients.

    El orden de la lista pasada es el orden de preferencia: el primero es el
    primario, los siguientes son fallbacks inversamente por prioridad.
    """

    def __init__(self, rerankers: Sequence[Reranker]) -> None:
        if not rerankers:
            raise ValueError("RerankerWithFallback requiere al menos un reranker")
        self._rerankers = list(rerankers)

    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        last_exc: Exception | None = None
        for i, reranker in enumerate(self._rerankers):
            try:
                return await reranker.rerank(query, candidates, top_k)
            except Exception as exc:  # noqa: BLE001
                status = _extract_http_status(exc)
                if status is not None:
                    if _is_transient_http_status(status):
                        logger.warning(
                            "Reranker #%d fallo con HTTP %d (transitorio), "
                            "intentando siguiente endpoint",
                            i,
                            status,
                        )
                        last_exc = exc
                        continue
                    # 4xx: error del cliente, no reintentar
                    raise
                elif isinstance(exc, _TRANSIENT_EXC):
                    logger.warning(
                        "Reranker #%d fallo con %s (transitorio), intentando siguiente endpoint",
                        i,
                        type(exc).__name__,
                    )
                    last_exc = exc
                    continue
                else:
                    # Otro error inesperado: propagar
                    raise

        # Todos fallaron con transitorio: propagar el ultimo error
        assert last_exc is not None  # noqa: S101 - invariant: len >= 1
        raise last_exc

    async def close(self) -> None:
        """Cierra todos los rerankers internos (best-effort)."""
        for reranker in self._rerankers:
            try:
                await reranker.close()
            except Exception:  # noqa: BLE001
                logger.debug("Error cerrando reranker en fallback", exc_info=True)
