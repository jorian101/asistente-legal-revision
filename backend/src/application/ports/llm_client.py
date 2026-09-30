"""Port: LLMClient — stub para Sprint 6 (Inyeccion LLM + generacion).

Sprint 6 implementa el adapter local (Ollama) que consume
ContextoExpandido y genera respuesta token-by-token.

Temperatura parametrica baja (configuracion_rag.temperatura o default 0.1)
para maximizar rigurosidad y adherencia legal.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from src.domain.value_objects.contexto_expandido import ContextoExpandido


class LLMClient(Protocol):
    """Port hacia Sprint 6 (Inyeccion LLM + generacion de respuesta).

    Sprint 6 implementa el adapter que consume ContextoExpandido y genera
    respuesta streaming token-by-token.
    """

    async def generar(
        self,
        prompt: str,
        contexto: ContextoExpandido,
        temperatura: float,
    ) -> AsyncIterator[str]:
        """Streaming token-by-token async iterator.

        Args:
            prompt: Plantilla resuelta (producida por ResolvedorPlantilla).
            contexto: Contexto expandido (producido por ExpansorContexto, S5).
            temperatura: Temperatura del modelo LLM.

        Yields:
            Tokens de texto generados secuencialmente.

        Raises:
            RuntimeError: Si el LLM no esta disponible o falla la generacion.
        """
        ...
