"""Caso de uso: listar ítems globales N2/N3 para los modales del chat.

Filtra normas por jerarquía (jurisprudencia/doctrina), solo activas e
indexadas. Lo consumen el JurisprudenciaModal y la sección libros del
DoctrinaModal (permiso doctrina-leer, no admin-corpus).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ItemCorpusGlobal:
    """Ítem global seleccionable (norma N2/N3)."""

    abreviatura: str
    nombre: str
    tipo: str
    jerarquia: str


class ListarCorpusPorJerarquia:
    """Lista normas globales de una jerarquía para selección por caso."""

    def __init__(self, norma_repo) -> None:
        self._norma_repo = norma_repo

    async def ejecutar(
        self, jerarquia: str, usuario_id: int | None = None
    ) -> list[ItemCorpusGlobal]:
        """Lista activas e indexadas de la jerarquía, ordenadas por nombre.

        Solo lo global y lo propio: una fuente privada o pendiente de otro no aparece.
        """
        normas = await self._norma_repo.list_all()
        items = [
            ItemCorpusGlobal(
                abreviatura=n.abreviatura,
                nombre=n.nombre,
                tipo=n.tipo,
                jerarquia=n.jerarquia,
            )
            for n in normas
            if n.jerarquia == jerarquia
            and n.activo
            and n.indexado
            and (
                n.estado_visibilidad == "global"
                or (
                    usuario_id is not None
                    and n.propietario_id == usuario_id
                    and n.estado_visibilidad in ("privado", "pendiente")
                )
            )
        ]
        return sorted(items, key=lambda i: i.nombre)
