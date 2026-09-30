"""Repositorio PostgreSQL: ChatRepoImpl.

Implementa el puerto application.ports.chat_repo.ChatRepo.
Mapea la entidad de dominio ChatPrivado ↔ modelo ORM ChatPrivadoModel.
"""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.chat_privado import ChatPrivadoModel
from src.application.ports.chat_repo import ChatRepo
from src.domain.entities.chat_privado import ChatPrivado
from src.domain.services.validador_propietario import validar_propietario_id


class ChatRepoImpl(ChatRepo):
    """Implementación PostgreSQL del repositorio de chats privados."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, chat: ChatPrivado) -> ChatPrivado:
        """Inserta un chat. Devuelve entidad con id y created_at asignados."""
        model = ChatPrivadoModel(
            expediente_id=chat.expediente_id,
            espacio_trabajo_id=chat.espacio_trabajo_id,
            propietario_id=chat.propietario_id,
            titulo=chat.titulo,
            estado=chat.estado,
            prioridad=chat.prioridad,
            contexto_legal=chat.contexto_legal,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        chat.id = model.id
        chat.created_at = model.created_at
        chat.updated_at = model.updated_at
        chat.ultimo_mensaje_at = model.ultimo_mensaje_at
        return chat

    async def obtener(self, chat_id: int, propietario_id: int) -> ChatPrivado | None:
        """Obtiene un chat por id, filtrando por propietario (Regla 5)."""
        validar_propietario_id(propietario_id)

        stmt = select(ChatPrivadoModel).where(
            ChatPrivadoModel.id == chat_id,
            ChatPrivadoModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def listar_por_usuario(
        self,
        usuario_id: int,
        expediente_id: int | None = None,
        estado: str | None = None,
    ) -> list[ChatPrivado]:
        """Lista chats del usuario. Filtros opcionales por expediente/estado."""
        validar_propietario_id(usuario_id)

        stmt = select(ChatPrivadoModel).where(ChatPrivadoModel.propietario_id == usuario_id)
        if expediente_id is not None:
            stmt = stmt.where(ChatPrivadoModel.expediente_id == expediente_id)
        if estado is not None:
            stmt = stmt.where(ChatPrivadoModel.estado == estado)

        stmt = stmt.order_by(
            ChatPrivadoModel.ultimo_mensaje_at.desc().nullslast(),
            ChatPrivadoModel.created_at.desc(),
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def actualizar_estado(
        self, chat_id: int, propietario_id: int, estado: str
    ) -> ChatPrivado | None:
        """Cambia el estado (activo/archivado/eliminado). Devuelve actualizado."""
        validar_propietario_id(propietario_id)

        stmt = select(ChatPrivadoModel).where(
            ChatPrivadoModel.id == chat_id,
            ChatPrivadoModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado = estado
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_ultimo_mensaje_at(
        self, chat_id: int, propietario_id: int
    ) -> ChatPrivado | None:
        """Marca el Timestamp del último mensaje. Devuelve chat actualizado."""
        validar_propietario_id(propietario_id)

        stmt = select(ChatPrivadoModel).where(
            ChatPrivadoModel.id == chat_id,
            ChatPrivadoModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        # utcnow: cargamos Timestamp en Python (sin SQL NOW() extra).
        # ponytail: más simple que scalar(text("NOW()")). Si hay drift de
        # reloj entre app y BD, migrar a server_default=NOW() on UPDATE.
        from datetime import datetime

        model.ultimo_mensaje_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: ChatPrivadoModel) -> ChatPrivado:
        return ChatPrivado(
            id=model.id,
            expediente_id=model.expediente_id,
            espacio_trabajo_id=model.espacio_trabajo_id,
            propietario_id=model.propietario_id,
            titulo=model.titulo,
            estado=model.estado,
            prioridad=model.prioridad,
            contexto_legal=model.contexto_legal,
            created_at=model.created_at,
            updated_at=model.updated_at,
            ultimo_mensaje_at=model.ultimo_mensaje_at,
        )


def get_chat_repo(session: AsyncSession) -> ChatRepo:
    """Factory para inyección de dependencias."""
    return ChatRepoImpl(session)
