"""Interactor: ListarNormas — Caso de uso de listado del corpus jurídico.

Devuelve todas las normas registradas (HU-04: admin lista normas y su estado
de indexación). Orquesta NormaRepo.list_all y mapea a DTO de salida.

Clean Architecture: dominio puro, sin I/O directo. Puerto inyectado.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.norma_repo import NormaRepo


@dataclass(slots=True)
class NormaResumenDTO:
    """DTO de salida: resumen de una norma para el listado del admin."""

    norma_id: int
    abreviatura: str
    nombre: str
    tipo: str
    jerarquia: str
    version: str | None
    indexado: bool
    indexado_por: int | None


class ListarNormas:
    """Caso de uso: Listar todas las normas del corpus jurídico."""

    ORDENES_VALIDOS = ("abreviatura", "nombre", "tipo", "jerarquia", "indexado")

    def __init__(self, norma_repo: NormaRepo) -> None:
        self._norma_repo = norma_repo

    async def ejecutar(self, orden: str = "abreviatura") -> list[NormaResumenDTO]:
        """Devuelve todas las normas ordenadas por el campo indicado (TI-01)."""
        if orden not in self.ORDENES_VALIDOS:
            raise ValueError(f"Orden '{orden}' invalido. Validos: {self.ORDENES_VALIDOS}")
        normas = await self._norma_repo.list_all()
        resumenes = [
            NormaResumenDTO(
                norma_id=n.id or 0,
                abreviatura=n.abreviatura,
                nombre=n.nombre,
                tipo=n.tipo,
                jerarquia=n.jerarquia,
                version=n.version,
                indexado=n.indexado,
                indexado_por=n.indexado_por,
            )
            for n in normas
        ]
        return sorted(resumenes, key=lambda r: getattr(r, orden))
