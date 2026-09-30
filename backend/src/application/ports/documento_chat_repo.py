"""Port: DocumentoChatRepo — Repositorio de documentos adjuntos (tabla `documento_chat`).

Protocols (structural typing) — las implementaciones no necesitan heredar.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.documento_chat import DocumentoChat


class DocumentoChatRepo(Protocol):
    """Repositorio de documentos adjuntos a mensajes de chat."""

    async def guardar(self, documento: DocumentoChat) -> DocumentoChat:
        """Registra un documento subido. Devuelve entidad con id y uploaded_at."""
        ...

    async def listar_por_chat(
        self,
        chat_id: int,
        usuario_id: int,
    ) -> list[DocumentoChat]:
        """Lista documentos de un chat del usuario (Regla 5: chat propio)."""
        ...

    async def marcar_procesamiento(
        self,
        documento_id: int,
        usuario_id: int,
        estado: str,
    ) -> DocumentoChat | None:
        """Cambia estado_procesamiento (pendiente/procesando/completado/fallido)."""
        ...
