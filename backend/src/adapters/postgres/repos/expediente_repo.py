"""Repositorio PostgreSQL: ExpedienteRepoImpl.

Implementa el puerto application.ports.expediente_repo.ExpedienteRepo.
Mapea la entidad de dominio Expediente ↔ modelo ORM ExpedienteModel.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.expediente import ExpedienteModel
from src.application.ports.expediente_repo import ExpedienteRepo
from src.domain.entities.expediente import Expediente
from src.domain.services.validador_propietario import validar_usuario_id


class ExpedienteRepoImpl(ExpedienteRepo):
    """Implementación PostgreSQL del repositorio de expedientes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, expediente: Expediente) -> Expediente:
        """Crea un expediente. Devuelve entidad con id y created_at asignados."""
        model = ExpedienteModel(
            numero_caso=expediente.numero_caso,
            tipo_proceso=expediente.tipo_proceso,
            tribunal_origen=expediente.tribunal_origen,
            procesado_nombre=expediente.procesado_nombre,
            procesado_grado=expediente.procesado_grado,
            delito=expediente.delito,
            sentencia_origen=expediente.sentencia_origen,
            fojas_total=expediente.fojas_total,
            estado=expediente.estado,
            abierto_por=expediente.abierto_por,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        expediente.id = model.id
        expediente.created_at = model.created_at
        return expediente

    async def obtener(self, expediente_id: int) -> Expediente | None:
        """Obtiene un expediente por PK. Sin filtro propietario (el ExpedienteModel
        no tiene propietario_id — lo tienen las Obras y los chats). Regla 5
        se aplica en `obra_repo` al listar obras del expediente.
        """
        stmt = select(ExpedienteModel).where(ExpedienteModel.id == expediente_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def obtener_por_numero_caso(self, numero_caso: str) -> Expediente | None:
        """Obtiene por UNIQUE numero_caso. None si no existe."""
        stmt = select(ExpedienteModel).where(ExpedienteModel.numero_caso == numero_caso)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def listar_por_usuario(
        self,
        usuario_id: int,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        """Lista expedientes abiertos por `usuario_id` (filtro `abierto_por`)."""
        validar_usuario_id(usuario_id)

        base = select(ExpedienteModel).where(ExpedienteModel.abierto_por == usuario_id)
        if estado is not None:
            base = base.where(ExpedienteModel.estado == estado)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(ExpedienteModel.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def listar_todos(
        self,
        *,
        incluir_archivados: bool = False,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        """Lista expedientes visibles (expedientes compartidos).

        - `incluir_archivados=True` (supervisor): todos los expedientes.
        - `incluir_archivados=False` (operador): solo `estado='activo'`.
        Restaura el comportamiento perdido del fix #322: todos los operadores
        ven los expedientes que el supervisor abre, mientras esten activos.
        """
        condiciones = []
        if not incluir_archivados:
            condiciones.append(ExpedienteModel.estado == "activo")
        if estado is not None:
            condiciones.append(ExpedienteModel.estado == estado)

        base = select(ExpedienteModel)
        if condiciones:
            base = base.where(*condiciones)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(ExpedienteModel.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def actualizar_estado(self, expediente_id: int, estado: str) -> Expediente | None:
        """Cambia estado (activo/archivado). Devuelve actualizado o None."""
        stmt = select(ExpedienteModel).where(ExpedienteModel.id == expediente_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado = estado
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar(
        self,
        expediente_id: int,
        *,
        numero_caso: str | None = None,
        procesado_nombre: str | None = None,
        delito: str | None = None,
        tribunal_origen: str | None = None,
        tipo_proceso: str | None = None,
    ) -> Expediente | None:
        """Actualiza metadatos de un expediente."""
        stmt = select(ExpedienteModel).where(ExpedienteModel.id == expediente_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        if numero_caso is not None:
            model.numero_caso = numero_caso
        if procesado_nombre is not None:
            model.procesado_nombre = procesado_nombre
        if delito is not None:
            model.delito = delito
        if tribunal_origen is not None:
            model.tribunal_origen = tribunal_origen
        if tipo_proceso is not None:
            model.tipo_proceso = tipo_proceso

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: ExpedienteModel) -> Expediente:
        return Expediente(
            id=model.id,
            numero_caso=model.numero_caso,
            tipo_proceso=model.tipo_proceso,
            tribunal_origen=model.tribunal_origen,
            procesado_nombre=model.procesado_nombre,
            procesado_grado=model.procesado_grado,
            delito=model.delito,
            sentencia_origen=model.sentencia_origen,
            fojas_total=model.fojas_total,
            estado=model.estado,
            abierto_por=model.abierto_por,
            created_at=model.created_at,
        )


def get_expediente_repo(session: AsyncSession) -> ExpedienteRepo:
    """Factory para inyección de dependencias."""
    return ExpedienteRepoImpl(session)
