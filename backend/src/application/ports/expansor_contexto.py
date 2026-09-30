"""Port: ExpansorContexto — stub para Sprint 5 (Expansion Jerarquica).

Sprint 5 implementa el adapter que, dado un ContextoRecuperado, asciende la
jerarquia usando padre_ref_id (PG self-ref) y padre_ref_key (payload Qdrant)
para construir el contexto expandido.

Regla Trail of Bits §6: breadcrumbs se resuelven contra PostgreSQL
(campo padre_ref_id FK self-referencial) — NO se confia en padre_ref_key
precalculado de Qdrant sin validacion contra PG.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado


class ExpansorContexto(Protocol):
    """Port hacia Sprint 5 (Expansion Jerarquica del Contexto).

    Sprint 5 implementa el adapter que, dado un ContextoRecuperado,
    asciende la jerarquia y retorna ContextoExpandido.
    """

    async def expandir(
        self,
        contexto: ContextoRecuperado,
        usuario_id: int,
    ) -> ContextoExpandido:
        """Recibe fragmentos rerankeados, retorna contexto expandido.

        Args:
            contexto: Output del PipelineRAG (Sprint 3).
            usuario_id: Regla 4 — filtra obrados privados.

        Returns:
            ContextoExpandido con fragmentos enriquecidos.
        """
        ...

    async def resolver_breadcrumbs(
        self,
        contexto: ContextoRecuperado,
        usuario_id: int,
    ) -> ContextoExpandido:
        """Resuelve breadcrumbs jerarquicos sin expandir el contexto (G6).

        Para consultas con expandir=False (ej. consulta_simple): construye
        la ruta jerarquica (padre_ref_key desde raiz hasta cada fragmento)
        via PG, SIN subir los padres al contexto. El LLM asi sabe
        "Art. X de Capitulo Y de Titulo Z" sin pagar tokens de expansion.

        Regla 6: los breadcrumbs se resuelven contra PG (padre_ref_id),
        no se confia en padre_ref_key de Qdrant sin validacion.

        Args:
            contexto: Output del PipelineRAG (fases 1-3).
            usuario_id: Regla 4 — filtra obrados privados.

        Returns:
            ContextoExpandido con los MISMOS fragmentos/scores que el
            contexto de entrada + breadcrumbs poblados y trazabilidad.
        """
        ...
