"""Port: MensajeChatRepo — Repositorio de mensajes de chat (tabla `mensaje_chat`).

Protocols (structural typing) — las implementaciones no necesitan heredar.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.mensaje_chat import MensajeChat


class MensajeChatRepo(Protocol):
    """Repositorio de mensajes de chat (tabla `mensaje_chat`)."""

    async def guardar(self, mensaje: MensajeChat) -> MensajeChat:
        """Agrega un mensaje a un chat. Devuelve entidad con id y created_at."""
        ...

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
        ...

    async def obtener_ultima_posicion(self, chat_id: int, usuario_id: int) -> int:
        """Devuelve la siguiente posicion libre en el chat (max+1). 0 si vacío."""
        ...
