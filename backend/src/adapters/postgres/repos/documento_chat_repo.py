"""Repositorio PostgreSQL: DocumentoChatRepoImpl.

Implementa el puerto application.ports.documento_chat_repo.DocumentoChatRepo.
Mapea la entidad de dominio DocumentoChat ↔ modelo ORM DocumentoChatModel.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.chat_privado import ChatPrivadoModel
from src.adapters.postgres.models.documento_chat import DocumentoChatModel
from src.application.ports.documento_chat_repo import DocumentoChatRepo
from src.domain.entities.documento_chat import DocumentoChat
from src.domain.services.validador_propietario import validar_usuario_id


class DocumentoChatRepoImpl(DocumentoChatRepo):
    """Implementación PostgreSQL del repositorio de documentos de chat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, documento: DocumentoChat) -> DocumentoChat:
        """Registra un documento subido. Devuelve entidad con id y uploaded_at."""
        model = DocumentoChatModel(
            chat_id=documento.chat_id,
            mensaje_id=documento.mensaje_id,
            usuario_id=documento.usuario_id,
            nombre_original=documento.nombre_original,
            tamano_archivo=documento.tamano_archivo,
            tipo_documento=documento.tipo_documento,
            estado_procesamiento=documento.estado_procesamiento,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        documento.id = model.id
        documento.uploaded_at = model.uploaded_at
        return documento

    async def listar_por_chat(
        self,
        chat_id: int,
        usuario_id: int,
    ) -> list[DocumentoChat]:
        """Lista documentos de un chat del usuario (Regla 5: chat propio)."""
        validar_usuario_id(usuario_id)

        # JOIN con chat_privado garantiza Regla 5 (no se listan documentos de
        # chats ajenos, aunque chat_id sea adivinado por input).
        stmt = (
            select(DocumentoChatModel)
            .join(ChatPrivadoModel, ChatPrivadoModel.id == DocumentoChatModel.chat_id)
            .where(
                DocumentoChatModel.chat_id == chat_id,
                ChatPrivadoModel.propietario_id == usuario_id,
            )
            .order_by(DocumentoChatModel.uploaded_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def marcar_procesamiento(
        self,
        documento_id: int,
        usuario_id: int,
        estado: str,
    ) -> DocumentoChat | None:
        """Cambia estado_procesamiento (pendiente/procesando/completado/fallido)."""
        validar_usuario_id(usuario_id)

        stmt = select(DocumentoChatModel).where(
            DocumentoChatModel.id == documento_id,
            DocumentoChatModel.usuario_id == usuario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado_procesamiento = estado
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: DocumentoChatModel) -> DocumentoChat:
        return DocumentoChat(
            id=model.id,
            chat_id=model.chat_id,
            mensaje_id=model.mensaje_id,
            usuario_id=model.usuario_id,
            nombre_original=model.nombre_original,
            tamano_archivo=model.tamano_archivo,
            tipo_documento=model.tipo_documento,
            estado_procesamiento=model.estado_procesamiento,
            uploaded_at=model.uploaded_at,
        )


def get_documento_chat_repo(session: AsyncSession) -> DocumentoChatRepo:
    """Factory para inyección de dependencias."""
    return DocumentoChatRepoImpl(session)
