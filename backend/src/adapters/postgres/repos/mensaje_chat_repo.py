"""Repositorio PostgreSQL: MensajeChatRepoImpl.

Implementa el puerto application.ports.mensaje_chat_repo.MensajeChatRepo.
Mapea la entidad de dominio MensajeChat ↔ modelo ORM MensajeChatModel.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.mensaje_chat import MensajeChatModel
from src.application.ports.mensaje_chat_repo import MensajeChatRepo
from src.domain.entities.mensaje_chat import MensajeChat
from src.domain.services.validador_propietario import validar_usuario_id


class MensajeChatRepoImpl(MensajeChatRepo):
    """Implementación PostgreSQL del repositorio de mensajes de chat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, mensaje: MensajeChat) -> MensajeChat:
        """Inserta un mensaje. Devuelve entidad con id y created_at asignados.

        Serializa por chat con `SELECT ... FOR UPDATE` sobre la fila del chat y calcula
        la posicion dentro del bloqueo: dos envios concurrentes no comparten posicion
        (el indice unico de visibles rechazaba el segundo con un 500).
        """
        from src.adapters.postgres.models.chat_privado import ChatPrivadoModel

        await self._session.execute(
            select(ChatPrivadoModel.id)
            .where(ChatPrivadoModel.id == mensaje.chat_id)
            .with_for_update()
        )
        mensaje.posicion = await self.obtener_ultima_posicion(mensaje.chat_id, mensaje.usuario_id)
        model = MensajeChatModel(
            chat_id=mensaje.chat_id,
            usuario_id=mensaje.usuario_id,
            tipo=mensaje.tipo,
            razonamiento=mensaje.razonamiento,
            contenido=mensaje.contenido,
            estado=mensaje.estado,
            posicion=mensaje.posicion,
            metadatos=mensaje.metadatos,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        mensaje.id = model.id
        mensaje.created_at = model.created_at
        mensaje.updated_at = model.updated_at
        return mensaje

    async def listar_por_chat(
        self,
        chat_id: int,
        usuario_id: int,
        pagina: int = 1,
        por_pagina: int = 50,
    ) -> tuple[list[MensajeChat], int]:
        """Lista mensajes visibles (activo/editado) de un chat del usuario.

        Args:
            chat_id: OBLIGATORIO.
            usuario_id: OBLIGATORIO (Regla 5: solo chats propios).
            pagina: 1-indexed.
            por_pagina: Tamaño de página.

        Returns:
            Tupla (items, total) — items ya paginados, ordenados por posicion.
        """
        validar_usuario_id(usuario_id)

        from src.adapters.postgres.models.chat_privado import ChatPrivadoModel

        base = (
            select(MensajeChatModel)
            .join(ChatPrivadoModel, ChatPrivadoModel.id == MensajeChatModel.chat_id)
            .where(
                MensajeChatModel.chat_id == chat_id,
                ChatPrivadoModel.propietario_id == usuario_id,
                MensajeChatModel.estado.in_(("activo", "editado")),
            )
        )
        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(MensajeChatModel.posicion.asc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def obtener_ultima_posicion(self, chat_id: int, usuario_id: int) -> int:
        """Devuelve la siguiente posición libre en el chat (max+1). 0 si vacío."""
        validar_usuario_id(usuario_id)

        from src.adapters.postgres.models.chat_privado import ChatPrivadoModel

        # JOIN con chat_privado garantiza Regla 5 (no se cuentan mensajes de
        # chats ajenos, aunque chat_id sea adivinado por input malicioso).
        stmt = (
            select(func.max(MensajeChatModel.posicion))
            .join(ChatPrivadoModel, ChatPrivadoModel.id == MensajeChatModel.chat_id)
            .where(
                MensajeChatModel.chat_id == chat_id,
                ChatPrivadoModel.propietario_id == usuario_id,
                MensajeChatModel.estado.in_(("activo", "editado")),
            )
        )
        result = await self._session.execute(stmt)
        max_pos = result.scalar()
        return (int(max_pos) + 1) if max_pos is not None else 0

    def _to_domain(self, model: MensajeChatModel) -> MensajeChat:
        return MensajeChat(
            id=model.id,
            chat_id=model.chat_id,
            usuario_id=model.usuario_id,
            tipo=model.tipo,
            razonamiento=model.razonamiento,
            contenido=model.contenido,
            estado=model.estado,
            posicion=model.posicion,
            metadatos=model.metadatos,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def get_mensaje_chat_repo(session: AsyncSession) -> MensajeChatRepo:
    """Factory para inyección de dependencias."""
    return MensajeChatRepoImpl(session)
