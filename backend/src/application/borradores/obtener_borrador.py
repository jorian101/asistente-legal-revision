"""Use case: ObtenerBorrador — obtiene un borrador por id con Regla 7.

Sprint 6 Fase 3.2. Obtiene el borrador + aplica la regla de visibilidad:
- Si estado='publicado' → cualquiera puede verlo.
- Si estado='borrador' → SOLO el propietario (Regla 7 BLOQUEANTE).
"""

from __future__ import annotations

from src.domain.entities.borrador import Borrador
from src.domain.exceptions import BorradorNoPropioError


class ObtenerBorrador:
    """Obtiene un borrador por id respetando la Regla 7 de visibilidad.

    Validacion en dominio (no router): el router solo mapea el error a 403.
    """

    def __init__(self, borrador_repo: object) -> None:
        self._repo = borrador_repo

    async def ejecutar(self, borrador_id: int, usuario_id: int) -> Borrador:
        """Devuelve el borrador o raise BorradorNoPropioError / ValueError.

        Raises:
            ValueError: Si el borrador no existe.
            BorradorNoPropioError: Si el borrador esta en estado 'borrador'
                y el usuario no es el propietario (Regla 7).
        """
        borrador = await self._repo.obtener_por_id(borrador_id)
        if borrador is None:
            raise ValueError(f"Borrador {borrador_id} no encontrado")
        if borrador.estado == "borrador" and borrador.propietario_id != usuario_id:
            raise BorradorNoPropioError(
                f"Usuario {usuario_id} no es propietario del borrador {borrador_id}"
            )
        return borrador


__all__ = ["ObtenerBorrador"]
