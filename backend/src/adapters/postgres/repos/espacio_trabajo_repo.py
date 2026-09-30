"""Repositorio PostgreSQL: EspacioTrabajoRepoImpl.

Implementa el puerto application.ports.espacio_trabajo_repo.EspacioTrabajoRepo.
Mapea la entidad de dominio EspacioTrabajo ↔ modelo ORM EspacioTrabajoModel.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.espacio_trabajo import EspacioTrabajoModel
from src.application.ports.espacio_trabajo_repo import EspacioTrabajoRepo
from src.domain.entities.espacio_trabajo import EspacioTrabajo
from src.domain.services.validador_propietario import validar_propietario_id


class EspacioTrabajoRepoImpl(EspacioTrabajoRepo):
    """Implementación PostgreSQL del repositorio de carpetas de chat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, espacio: EspacioTrabajo) -> EspacioTrabajo:
        """Crea una carpeta. Devuelve entidad con id asignado."""
        model = EspacioTrabajoModel(
            expediente_id=espacio.expediente_id,
            propietario_id=espacio.propietario_id,
            nombre=espacio.nombre,
            tipo=espacio.tipo,
            estado=espacio.estado,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        espacio.id = model.id
        espacio.created_at = model.created_at
        espacio.updated_at = model.updated_at
        return espacio

    async def obtener(self, espacio_id: int, propietario_id: int) -> EspacioTrabajo | None:
        """Obtiene una carpeta por id, filtrando por propietario (Regla 5)."""
        validar_propietario_id(propietario_id)

        stmt = select(EspacioTrabajoModel).where(
            EspacioTrabajoModel.id == espacio_id,
            EspacioTrabajoModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def listar_por_expediente(
        self,
        expediente_id: int,
        propietario_id: int,
        estado: str | None = "activo",
    ) -> list[EspacioTrabajo]:
        """Lista carpetas del usuario dentro de un expediente."""
        validar_propietario_id(propietario_id)

        stmt = select(EspacioTrabajoModel).where(
            EspacioTrabajoModel.expediente_id == expediente_id,
            EspacioTrabajoModel.propietario_id == propietario_id,
        )
        if estado is not None:
            stmt = stmt.where(EspacioTrabajoModel.estado == estado)

        stmt = stmt.order_by(EspacioTrabajoModel.created_at.asc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def cambiar_tipo(
        self, espacio_id: int, propietario_id: int, tipo: str
    ) -> EspacioTrabajo | None:
        """Cambia el tipo (fijado/archivado/personalizado). Devuelve actualizado."""
        validar_propietario_id(propietario_id)

        stmt = select(EspacioTrabajoModel).where(
            EspacioTrabajoModel.id == espacio_id,
            EspacioTrabajoModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.tipo = tipo
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: EspacioTrabajoModel) -> EspacioTrabajo:
        return EspacioTrabajo(
            id=model.id,
            expediente_id=model.expediente_id,
            propietario_id=model.propietario_id,
            nombre=model.nombre,
            tipo=model.tipo,
            estado=model.estado,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def get_espacio_trabajo_repo(session: AsyncSession) -> EspacioTrabajoRepo:
    """Factory para inyección de dependencias."""
    return EspacioTrabajoRepoImpl(session)
