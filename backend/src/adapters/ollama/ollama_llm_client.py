"""Adapter: OllamaLLMClient — LLM streaming via Ollama /api/generate.

Sprint 6 Fase 2.2. Implementa LLMClient (port).

Streaming token-by-token usando httpx.AsyncClient against /api/generate
with stream=true. Cada chunk JSON trae {"response": <token>, "done": bool}.

Ponytail: httpx ya es dependencia (OllamaEmbedder la usa). Sin SDK ollama-python,
sin WebSocket/SSE, sin pool de conexiones — un AsyncClient por llamada.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx

from src.application.services.constructor_mensajes import ConstructorMensajes
from src.domain.value_objects.contexto_expandido import ContextoExpandido

if TYPE_CHECKING:
    pass


class OllamaLLMClient:
    """LLM streaming contra Ollama /api/generate.

    Args:
        base_url: Host de Ollama (ej. http://localhost:11434).
        model: Nombre del modelo (ej. llama3:8b).
        timeout: Timeout HTTP en segundos (default settings: 300).
        presupuesto_tokens: Presupuesto aproximado de tokens para el
            bloque de contexto (ConstructorMensajes, F2).
        soporta_system: False si el endpoint no soporta mensaje de sistema
            (se pliega al user). Default True.
        ventana_tokens: num_ctx enviado a Ollama y ventana contra la que se
            presupuesta el contexto. Default 8192 (maximo nativo de llama3:8b);
            otro modelo u hardware lo declara con context_window_tokens.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        presupuesto_tokens: int = 4096,
        soporta_system: bool = True,
        ventana_tokens: int = 8192,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        # Fijo por endpoint: si num_ctx cambiara entre pedidos, Ollama recargaria
        # el modelo en cada uno. Sin el, Ollama usa su default (4096) y trunca.
        self._num_ctx = ventana_tokens
        self._constructor = ConstructorMensajes(
            presupuesto_tokens=presupuesto_tokens,
            soporta_system=soporta_system,
            ventana_tokens=ventana_tokens,
        )

    async def generar(
        self,
        prompt: str,
        contexto: ContextoExpandido,
        temperatura: float,
    ) -> AsyncIterator[str]:
        """Stream tokens del LLM inyectando contexto juridico en el prompt.

        Raises:
            RuntimeError: Si Ollama responde >=400 o falla la conexion.
        """
        mensajes = self._constructor.construir(prompt, contexto)
        payload: dict = {
            "model": self._model,
            "prompt": mensajes.user,
            "stream": True,
            "options": {"temperature": temperatura, "num_ctx": self._num_ctx},
        }
        if mensajes.system is not None:
            # /api/generate acepta system como campo separado del prompt.
            payload["system"] = mensajes.system
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:  # noqa: SIM117
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        if token := chunk.get("response", ""):
                            yield token
                        if chunk.get("done"):
                            return
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama /api/generate fallo HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Ollama /api/generate no disponible") from exc


__all__ = ["OllamaLLMClient"]
