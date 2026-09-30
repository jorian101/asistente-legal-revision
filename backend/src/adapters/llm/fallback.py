"""LLMWithFallback — wrapper que itera endpoints LLM ante errores transitorios.

Mirror de RerankerWithFallback pero para LLM streaming.

Orden de preferencia: la lista pasada es el orden primario -> fallback.
Si el primario falla con 503/429/5xx/timeout/network, prueba el siguiente.
Errores 4xx (auth, validación) se propagan directo.

Transparente para GenerarBorrador: implementa LLMClient.generar().
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Sequence

import httpx

from src.application.ports.llm_client import LLMClient

logger = logging.getLogger(__name__)

_TRANSIENT_EXC = (httpx.TimeoutException, httpx.NetworkError)
_HTTP_STATUS_RE = re.compile(r"HTTP\s+(\d{3})")


def _extract_http_status(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    if isinstance(exc, RuntimeError):
        m = _HTTP_STATUS_RE.search(str(exc))
        if m:
            return int(m.group(1))
    return None


def _is_transient(status: int) -> bool:
    # 5xx + 429 son transitorios clásicos. Para LLM, 404/410 (modelo deprecado)
    # también debe hacer fallback al siguiente endpoint.
    return status >= 500 or status in (429, 404, 410)


class LLMWithFallback(LLMClient):
    """LLM que prueba endpoints en orden y cae al siguiente ante transients."""

    def __init__(self, clients: Sequence[LLMClient]) -> None:
        if not clients:
            raise ValueError("LLMWithFallback requiere al menos un LLMClient")
        self._clients = list(clients)
        # Modelo del que respondio efectivamente (para telemetria/Sala). Default
        # al primero; se actualiza en generar() cuando un endpoint completa.
        self.model_respuesta: str = str(getattr(clients[0], "_model", "desconocido"))

    async def generar(
        self,
        prompt: str,
        contexto,  # ContextoExpandido
        temperatura: float,
    ) -> AsyncIterator[str]:
        last_exc: Exception | None = None
        for idx, client in enumerate(self._clients):
            try:
                async for token in client.generar(prompt, contexto, temperatura):
                    yield token
                self.model_respuesta = str(getattr(client, "_model", self.model_respuesta))
                return
            except Exception as exc:  # noqa: BLE001
                status = _extract_http_status(exc)
                is_transient = (
                    (status is not None and _is_transient(status))
                    or isinstance(exc, _TRANSIENT_EXC)
                    or (status is None and isinstance(exc, RuntimeError) and "503" in str(exc))
                )
                # Also treat our fallback message as non-transient? No, we already handle.
                if is_transient:
                    logger.warning(
                        "LLM #%d (%s) fallo transitorio %s, probando siguiente",
                        idx,
                        getattr(client, "_model", "unknown"),
                        f"HTTP {status}" if status else type(exc).__name__,
                    )
                    last_exc = exc
                    continue
                # 4xx or non-transient -> propagate immediately
                raise
        # Todos fallaron
        assert last_exc is not None  # noqa: S101
        raise last_exc
