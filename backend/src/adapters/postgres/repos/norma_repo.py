"""Adapter: SQL NormaRepo — Repositorio de normas para PostgreSQL.

Implementa NormaRepo usando SQLAlchemy async + ORM models.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.norma import NormaModel
from src.application.ports.norma_repo import NormaRepo
from src.domain.entities.norma import Norma


class SqlNormaRepo(NormaRepo):
    """Implementación concreta de NormaRepo para PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, norma: Norma) -> Norma:
        """Inserta o actualiza una Norma. Devuelve Norma con ID asignado."""
        model = NormaModel(
            nombre=norma.nombre,
            abreviatura=norma.abreviatura,
            tipo=norma.tipo,
            jerarquia=norma.jerarquia,
            version=norma.version,
            ruta_archivo=norma.ruta_archivo,
            indexado=norma.indexado,
            indexado_por=norma.indexado_por,
            propietario_id=norma.propietario_id,
            estado_visibilidad=norma.estado_visibilidad,
            motivo_rechazo=norma.motivo_rechazo,
            origen_obra_id=norma.origen_obra_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)

        norma.id = model.id
        norma.created_at = model.created_at
        return norma

    async def get_by_id(self, norma_id: int) -> Norma | None:
        """Obtiene Norma por PK."""
        stmt = select(NormaModel).where(NormaModel.id == norma_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def get_by_abreviatura(self, abreviatura: str) -> Norma | None:
        """Obtiene Norma por abreviatura única (UNIQUE constraint)."""
        stmt = select(NormaModel).where(NormaModel.abreviatura == abreviatura)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def list_all(self) -> list[Norma]:
        """Lista normas activas ordenadas por abreviatura (soft delete CRITICAL #3)."""
        stmt = (
            select(NormaModel)
            .where(NormaModel.activo == True)  # noqa: E712
            .order_by(NormaModel.abreviatura)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def marcar_indexada(self, norma_id: int, indexado_por: int | None) -> None:
        """Marca Norma como indexada (indexado=True, indexado_por=usuario)."""
        stmt = select(NormaModel).where(NormaModel.id == norma_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Norma con id {norma_id} no encontrada")
        model.indexado = True
        model.indexado_por = indexado_por
        await self._session.flush()

    async def eliminar_soft(self, norma_id: int) -> bool:
        """Soft delete: activo=False (CRITICAL #3). True si existia y activa."""
        stmt = select(NormaModel).where(
            NormaModel.id == norma_id,
            NormaModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False

        model.activo = False
        await self._session.flush()
        await self._session.commit()
        return True

    async def actualizar(
        self,
        norma_id: int,
        *,
        nombre: str | None = None,
        version: str | None = None,
    ) -> Norma | None:
        """Actualiza metadatos de una norma."""
        stmt = select(NormaModel).where(
            NormaModel.id == norma_id,
            NormaModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None

        if nombre is not None:
            model.nombre = nombre
        if version is not None:
            model.version = version

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_visibilidad(
        self, norma_id: int, estado: str, motivo_rechazo: str | None = None
    ) -> Norma | None:
        """Cambia el estado de visibilidad (proponer / aprobar / rechazar)."""
        stmt = select(NormaModel).where(
            NormaModel.id == norma_id,
            NormaModel.activo == True,  # noqa: E712
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        model.estado_visibilidad = estado
        model.motivo_rechazo = motivo_rechazo
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: NormaModel) -> Norma:
        """Convierte modelo ORM -> entidad de dominio."""
        return Norma(
            id=model.id,
            nombre=model.nombre,
            abreviatura=model.abreviatura,
            tipo=model.tipo,
            jerarquia=model.jerarquia,
            version=model.version,
            ruta_archivo=model.ruta_archivo,
            indexado=model.indexado,
            indexado_por=model.indexado_por,
            activo=model.activo,
            created_at=model.created_at,
            propietario_id=model.propietario_id,
            estado_visibilidad=model.estado_visibilidad,
            motivo_rechazo=model.motivo_rechazo,
            origen_obra_id=model.origen_obra_id,
        )


def get_norma_repo(session: AsyncSession) -> NormaRepo:
    """Factory para inyección de dependencias."""
    return SqlNormaRepo(session)
