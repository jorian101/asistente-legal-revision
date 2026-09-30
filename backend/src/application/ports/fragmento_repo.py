"""Port: FragmentoRepo — Repositorio de fragmentos (tabla `fragmento`).

Protocols (structural typing) — las implementaciones no necesitan heredar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.fragmento import Fragmento


@dataclass(frozen=True, slots=True)
class PaginaFragmentos:
    """Pagina de fragmentos con total (para el tab Segmentos de la UI)."""

    items: list[Fragmento]
    total: int
    pagina: int
    por_pagina: int


class FragmentoRepo(Protocol):
    """Repositorio de fragmentos (tabla `fragmento`)."""

    async def save(self, fragmento: Fragmento) -> Fragmento:
        """Inserta un fragmento. Devuelve fragmento con ID y qdrant_point_id."""
        ...

    async def save_many(self, fragmentos: list[Fragmento]) -> list[Fragmento]:
        """Inserta lote de fragmentos (batch)."""
        ...

    async def asignar_padres_por_ids(self, pares: list[tuple[int, int]]) -> None:
        """Asigna padre_ref_id en lote: pares (id_hijo, id_padre) (D-S5K-01).

        El enlace que el expansor recorre via CTE (Regla 6). Sin SELECT
        previo: UPDATE batch por clave primaria.
        """
        ...

    async def get_by_norma(self, norma_id: int) -> list[Fragmento]:
        """Obtiene todos los fragmentos de una norma."""
        ...

    async def get_articulos(self, pares: list[tuple[str, int]]) -> list[Fragmento]:
        """Fragmentos de los artículos (abreviatura, número) de normas globales activas.

        Por artículo, el fragmento del artículo entero si existe; si no, sus numerales.
        """
        ...

    async def delete_by_obra(self, obra_id: int) -> int:
        """Elimina los fragmentos de una obra antes de reindexarla."""
        ...

    async def get_by_qdrant_ids(self, qdrant_ids: list[str]) -> list[Fragmento]:
        """Obtiene fragmentos por lista de qdrant_point_id (busqueda hibrida)."""
        ...

    async def delete_by_norma(self, norma_id: int) -> int:
        """Borra todos los fragmentos de una norma. Devuelve count."""
        ...

    async def count_by_norma(self, norma_id: int) -> int:
        """Cuenta los fragmentos de una norma (sin hidratarlos)."""
        ...

    async def list_all_qdrant_ids(self) -> list[str]:
        """Devuelve todos los qdrant_point_id en PG (para reconciliacion)."""
        ...

    async def list_fragmentos(
        self,
        pagina: int = 1,
        por_pagina: int = 10,
        norma_id: int | None = None,
        tipo_chunk: str | None = None,
        nivel_jerarquico: int | None = None,
        texto: str | None = None,
    ) -> PaginaFragmentos:
        """Devuelve una pagina de fragmentos con total, aplicando filtros."""
        ...

    async def get_ascendencia(
        self,
        fragmento_ids: list[int],
        max_depth: int,
    ) -> list[Fragmento]:
        """Obtiene los ancestros jerarquicos de los fragmentos dados.

        Sprint 5 (Regla 6 BLOQUEANTE): la ascendencia se resuelve contra
        PostgreSQL (FK self-ref `fragmento.padre_ref_id`), NO contra
        `padre_ref_key` del payload de Qdrant. Implementacion esperada:
        CTE recursivo.

        Args:
            fragmento_ids: IDs de fragmentos hoja (los que ya estan en
                ContextoRecuperado). Excluidos del resultado.
            max_depth: Profundidad maxima del BFS ascendente.

        Returns:
            Lista de Fragmento ascendidos (sin duplicados), excluyendo las
            hojas originales. Orden no garantizado; el caller deduplica
            si lo necesita.
        """
        ...

    async def listar_vocabulario(self) -> frozenset[str]:
        """Retorna los tokens unicos del corpus (Capa A, correccion de typos).

        Se usa para corregir typos de la query del usuario por edit-distance
        contra el vocabulario real del corpus, en vez de un diccionario fijo
        (anti-overfit). La implementacion cachea por proceso.
        """
        ...

    async def get_by_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        limit: int = 20,
    ) -> list[Fragmento]:
        """Obtiene fragmentos de obrados de un expediente visibles para el usuario.

        Usado como fallback para borradores cuando la búsqueda vectorial no
        retorna obrados (score bajo por OCR). Respeta Regla 5: solo obras
        publicadas/globales o privadas propias.
        """
        ...
