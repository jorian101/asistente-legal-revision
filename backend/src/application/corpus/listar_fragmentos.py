"""Interactor: ListarFragmentos — Listado paginado de fragmentos del corpus.

HU-04 extendida: el admin consulta los segmentos del corpus (tab "Segmentos"
de la UI), con filtros por norma, tipo de chunk, nivel jerarquico y texto.
Orquesta FragmentoRepo.list_fragmentos.

Clean Architecture: dominio puro, sin I/O directo. Puerto inyectado.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.fragmento_repo import FragmentoRepo


@dataclass(slots=True)
class ListarFragmentosRequest:
    """Entrada del caso de uso ListarFragmentos."""

    pagina: int = 1
    por_pagina: int = 10
    norma_id: int | None = None
    tipo_chunk: str | None = None
    nivel_jerarquico: int | None = None
    texto: str | None = None


@dataclass(slots=True)
class FragmentoDTO:
    """Salida: vista de un fragmento para la UI del admin."""

    id: int
    norma_id: int | None
    qdrant_point_id: str
    texto: str
    padre_ref_key: str | None
    nivel_jerarquico: int | None
    tipo_chunk: str | None


@dataclass(slots=True)
class PaginaFragmentosDTO:
    """Salida: pagina de fragmentos con metadatos de paginacion."""

    items: list[FragmentoDTO]
    total: int
    pagina: int
    por_pagina: int


# Limites de seguridad (proteccion contra paginacion abusiva).
MAX_POR_PAGINA = 50
MIN_POR_PAGINA = 1


class ListarFragmentos:
    """Caso de uso: Listar fragmentos del corpus con filtros y paginacion."""

    def __init__(self, fragmento_repo: FragmentoRepo) -> None:
        self._fragmento_repo = fragmento_repo

    async def ejecutar(self, request: ListarFragmentosRequest) -> PaginaFragmentosDTO:
        """Devuelve una pagina de fragmentos, aplicando filtros y limites."""
        pagina = max(request.pagina, 1)
        por_pagina = min(max(request.por_pagina, MIN_POR_PAGINA), MAX_POR_PAGINA)

        pagina_result = await self._fragmento_repo.list_fragmentos(
            pagina=pagina,
            por_pagina=por_pagina,
            norma_id=request.norma_id,
            tipo_chunk=request.tipo_chunk,
            nivel_jerarquico=request.nivel_jerarquico,
            texto=request.texto,
        )

        return PaginaFragmentosDTO(
            items=[
                FragmentoDTO(
                    id=f.id or 0,
                    norma_id=f.norma_id,
                    qdrant_point_id=f.qdrant_point_id,
                    texto=f.texto,
                    padre_ref_key=f.padre_ref_key,
                    nivel_jerarquico=f.nivel_jerarquico,
                    tipo_chunk=getattr(f, "tipo_chunk", None),
                )
                for f in pagina_result.items
            ],
            total=pagina_result.total,
            pagina=pagina_result.pagina,
            por_pagina=pagina_result.por_pagina,
        )
