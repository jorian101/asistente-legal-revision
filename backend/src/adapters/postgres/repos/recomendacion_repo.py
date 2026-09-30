"""Repositorio PostgreSQL: RecomendacionRepoImpl.

Implementa el puerto application.ports.recomendacion_repo.RecomendacionRepo.
Mapea la entidad RecomendacionDoctrina ↔ modelo ORM RecomendacionDoctrinaModel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.recomendacion_doctrina import (
    RecomendacionDoctrinaModel,
)
from src.application.ports.recomendacion_repo import RecomendacionRepo
from src.domain.entities.recomendacion_doctrina import RecomendacionDoctrina


class RecomendacionRepoImpl(RecomendacionRepo):
    """Implementación PostgreSQL del repositorio de recomendaciones."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recomendar(
        self,
        *,
        obra_global_id: int | None,
        expediente_id: int,
        recomendado_por: int,
        estado: str,
        corpus: str | None = None,
        corpus_ref: str | None = None,
    ) -> RecomendacionDoctrina:
        if obra_global_id is None:
            if not corpus or not corpus_ref:
                raise ValueError("recomendar por corpus requiere corpus y corpus_ref")
            stmt = select(RecomendacionDoctrinaModel).where(
                RecomendacionDoctrinaModel.obra_global_id.is_(None),
                RecomendacionDoctrinaModel.expediente_id == expediente_id,
                RecomendacionDoctrinaModel.corpus == corpus,
                RecomendacionDoctrinaModel.corpus_ref == corpus_ref,
            )
        else:
            stmt = select(RecomendacionDoctrinaModel).where(
                RecomendacionDoctrinaModel.obra_global_id == obra_global_id,
                RecomendacionDoctrinaModel.expediente_id == expediente_id,
            )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            # Dedup cruzado obra<->corpus: el mismo ítem N2/N3 recomendado
            # por la otra vía actualiza la fila existente en vez de duplicar
            # en el modal (una sola entrada por ítem y expediente).
            model = await self._buscar_duplicada_cruzada(
                obra_global_id, expediente_id, corpus, corpus_ref
            )
        if model is None:
            model = RecomendacionDoctrinaModel(
                obra_global_id=obra_global_id,
                expediente_id=expediente_id,
                recomendado_por=recomendado_por,
                estado=estado,
                corpus=corpus,
                corpus_ref=corpus_ref,
            )
            self._session.add(model)
        else:
            model.estado = estado
            model.recomendado_por = recomendado_por
            model.aprobado_por = None
            model.motivo_rechazo = None
            model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def _buscar_duplicada_cruzada(
        self,
        obra_global_id: int | None,
        expediente_id: int,
        corpus: str | None,
        corpus_ref: str | None,
    ):
        """Busca recomendación del mismo ítem por la vía contraria.

        - Vía corpus -> ¿existe rec por obra cuyo puntero tenga ese ref?
        - Vía obra (puntero con ref) -> ¿existe rec por corpus con ese ref?
        None si no hay duplicada.
        """
        from src.adapters.postgres.models.obra import ObraModel

        if obra_global_id is None:
            stmt = (
                select(RecomendacionDoctrinaModel)
                .join(ObraModel, ObraModel.id == RecomendacionDoctrinaModel.obra_global_id)
                .where(
                    RecomendacionDoctrinaModel.expediente_id == expediente_id,
                    ObraModel.corpus_ref == corpus_ref,
                )
            )
        else:
            ref_stmt = select(ObraModel.corpus_ref).where(ObraModel.id == obra_global_id)
            ref_result = await self._session.execute(ref_stmt)
            ref = ref_result.scalar_one_or_none()
            if not ref:
                return None
            stmt = select(RecomendacionDoctrinaModel).where(
                RecomendacionDoctrinaModel.obra_global_id.is_(None),
                RecomendacionDoctrinaModel.expediente_id == expediente_id,
                RecomendacionDoctrinaModel.corpus_ref == ref,
            )
        result = await self._session.execute(stmt)
        return result.scalars().one_or_none()

    async def listar_por_expediente(
        self,
        expediente_id: int,
        *,
        solo_aprobadas: bool = True,
    ) -> list[RecomendacionDoctrina]:
        condiciones = [RecomendacionDoctrinaModel.expediente_id == expediente_id]
        if solo_aprobadas:
            condiciones.append(RecomendacionDoctrinaModel.estado == "recomendada")
        stmt = select(RecomendacionDoctrinaModel).where(*condiciones)
        stmt = stmt.order_by(RecomendacionDoctrinaModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def listar_pendientes(
        self,
        *,
        filtro: str | None = None,
    ) -> list[RecomendacionDoctrina]:
        condiciones = [RecomendacionDoctrinaModel.estado == "pendiente"]
        stmt = select(RecomendacionDoctrinaModel).where(*condiciones)
        stmt = stmt.order_by(RecomendacionDoctrinaModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def aprobar(
        self,
        recomendacion_id: int,
        aprobado_por: int,
    ) -> RecomendacionDoctrina | None:
        stmt = select(RecomendacionDoctrinaModel).where(
            RecomendacionDoctrinaModel.id == recomendacion_id,
            RecomendacionDoctrinaModel.estado == "pendiente",
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None
        model.estado = "recomendada"
        model.aprobado_por = aprobado_por
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def rechazar(
        self,
        recomendacion_id: int,
        aprobado_por: int,
        motivo: str,
    ) -> RecomendacionDoctrina | None:
        stmt = select(RecomendacionDoctrinaModel).where(
            RecomendacionDoctrinaModel.id == recomendacion_id,
            RecomendacionDoctrinaModel.estado == "pendiente",
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None
        model.estado = "rechazada"
        model.aprobado_por = aprobado_por
        model.motivo_rechazo = motivo
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def aprobar_todas(
        self,
        aprobado_por: int,
        *,
        ids: list[int] | None = None,
    ) -> int:
        from sqlalchemy import update

        if ids is not None and not ids:
            return 0  # seleccion vacia: no es "todas"
        stmt = update(RecomendacionDoctrinaModel).where(
            RecomendacionDoctrinaModel.estado == "pendiente"
        )
        if ids is not None:
            stmt = stmt.where(RecomendacionDoctrinaModel.id.in_(ids))
        stmt = stmt.values(
            estado="recomendada",
            aprobado_por=aprobado_por,
            updated_at=datetime.now(UTC),
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount or 0

    def _to_domain(self, model: RecomendacionDoctrinaModel) -> RecomendacionDoctrina:
        return RecomendacionDoctrina(
            id=model.id,
            obra_global_id=model.obra_global_id,
            expediente_id=model.expediente_id,
            recomendado_por=model.recomendado_por,
            estado=model.estado,  # type: ignore[arg-type]
            aprobado_por=model.aprobado_por,
            motivo_rechazo=model.motivo_rechazo,
            created_at=model.created_at,
            updated_at=model.updated_at,
            corpus=model.corpus,
            corpus_ref=model.corpus_ref,
        )


def get_recomendacion_repo(session: AsyncSession) -> RecomendacionRepo:
    """Factory para inyección de dependencias."""
    return RecomendacionRepoImpl(session)
