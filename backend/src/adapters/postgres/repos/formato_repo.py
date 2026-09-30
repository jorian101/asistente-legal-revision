"""Repositorio PostgreSQL: FormatoRepoImpl."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.formato_documento import FormatoDocumentoModel
from src.application.ports.formato_repo import FormatoRepo
from src.domain.entities.formato_documento import FormatoDocumento


class FormatoRepoImpl(FormatoRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, formato: FormatoDocumento) -> FormatoDocumento:
        model = FormatoDocumentoModel(
            tipo_documento=formato.tipo_documento,
            slug=formato.slug,
            autor=formato.autor,
            engine=formato.engine,
            estado=formato.estado,
            version=formato.version,
            meta=formato.meta,
            bloques=formato.bloques,
            esqueleto=formato.esqueleto,
            hash_fuente=formato.hash_fuente,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()
        return self._to_domain(model)

    async def obtener(self, formato_id: int) -> FormatoDocumento | None:
        stmt = select(FormatoDocumentoModel).where(FormatoDocumentoModel.id == formato_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model else None

    async def obtener_por_slug(self, slug: str) -> FormatoDocumento | None:
        stmt = select(FormatoDocumentoModel).where(FormatoDocumentoModel.slug == slug)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model else None

    async def listar(
        self,
        *,
        tipo_documento: str | None = None,
        autor: str | None = None,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[FormatoDocumento], int]:
        base = select(FormatoDocumentoModel)
        if tipo_documento is not None:
            base = base.where(FormatoDocumentoModel.tipo_documento == tipo_documento)
        if autor is not None:
            base = base.where(FormatoDocumentoModel.autor == autor)
        if estado is not None:
            base = base.where(FormatoDocumentoModel.estado == estado)
        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)
        stmt = (
            base.order_by(
                FormatoDocumentoModel.updated_at.desc().nulls_last(),
                FormatoDocumentoModel.created_at.desc(),
            )
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def actualizar(self, formato: FormatoDocumento) -> FormatoDocumento:
        if formato.id is None:
            msg = "Formato sin id no se puede actualizar"
            raise ValueError(msg)
        stmt = select(FormatoDocumentoModel).where(FormatoDocumentoModel.id == formato.id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            msg = f"Formato {formato.id} no encontrado"
            raise ValueError(msg)
        model.tipo_documento = formato.tipo_documento
        model.slug = formato.slug
        model.autor = formato.autor
        model.engine = formato.engine
        model.estado = formato.estado
        model.version = formato.version
        model.meta = formato.meta
        model.bloques = formato.bloques
        model.esqueleto = formato.esqueleto
        model.hash_fuente = formato.hash_fuente
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def eliminar(self, formato_id: int) -> bool:
        stmt = select(FormatoDocumentoModel).where(FormatoDocumentoModel.id == formato_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.commit()
        return True

    def _to_domain(self, model: FormatoDocumentoModel) -> FormatoDocumento:
        return FormatoDocumento(
            id=model.id,
            tipo_documento=model.tipo_documento,  # type: ignore[arg-type]
            slug=model.slug,
            autor=model.autor,  # type: ignore[arg-type]
            engine=model.engine,
            meta=model.meta or {},
            bloques=model.bloques or [],
            esqueleto=model.esqueleto,
            estado=model.estado,  # type: ignore[arg-type]
            version=model.version,
            hash_fuente=model.hash_fuente,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def get_formato_repo(session: AsyncSession) -> FormatoRepo:
    return FormatoRepoImpl(session)
