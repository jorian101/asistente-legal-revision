"""Use case: ListarBorradores — lista borradores de un expediente.

Sprint 6 Fase 3.2. Wrapper fino sobre BorradorRepo.listar_por_expediente:
Regla 7 (filtro por propietario_id) vive en el adapter (no en el use case).
"""

from __future__ import annotations

from src.domain.entities.borrador import Borrador


class ListarBorradores:
    """Lista borradores de un expediente filtrados por propietario.

    El filtro `propietario_id == usuario_id` lo aplica el adapter
    (BorradorRepoImpl) — Regla 7 Trail of Bits (filtro en la query SQL,
    no en el use case).
    """

    def __init__(self, borrador_repo: object) -> None:
        self._repo = borrador_repo

    async def ejecutar(self, expediente_id: int, usuario_id: int) -> list[Borrador]:
        return await self._repo.listar_por_expediente(expediente_id, usuario_id)


__all__ = ["ListarBorradores"]
