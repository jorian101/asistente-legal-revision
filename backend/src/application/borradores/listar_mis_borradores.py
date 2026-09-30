"""Use case: ListarMisBorradores — lista los borradores del propietario.

Vista 'Mis Borradores' (ex-interfaz Borradores rediseñada tipo Conversaciones).
Sin exigir expediente: devuelve todos los borradores del usuario actual,
ordenados por updated_at desc.

Regla 7 (BLOQUEANTE): el filtro propietario_id == usuario_id vive en el
adapter (la query SQL).
"""

from __future__ import annotations

from src.domain.entities.borrador import Borrador


class ListarMisBorradores:
    """Lista todos los borradores del propietario actual."""

    def __init__(self, borrador_repo: object) -> None:
        self._repo = borrador_repo

    async def ejecutar(self, propietario_id: int) -> list[Borrador]:
        return await self._repo.listar_por_propietario(propietario_id)


__all__ = ["ListarMisBorradores"]
