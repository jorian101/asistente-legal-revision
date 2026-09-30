"""Port: ChatRepo — Repositorio de chats privados (tabla `chat_privado`).

Protocols (structural typing) — las implementaciones no necesitan heredar.

Sprint 4 (Opción B fork #133): backend de chats reemplaza chatStore
localStorage del sidebar del Asistente. `consulta_historial` sigue como
log inmutable de auditoría/KPIs.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.chat_privado import ChatPrivado


class ChatRepo(Protocol):
    """Repositorio de chats privados (tabla `chat_privado`)."""

    async def guardar(self, chat: ChatPrivado) -> ChatPrivado:
        """Crea un chat. Devuelve entidad con id y created_at asignados."""
        ...

    async def obtener(self, chat_id: int, propietario_id: int) -> ChatPrivado | None:
        """Obtiene un chat por id, filtrando por propietario (Regla 5)."""
        ...

    async def listar_por_usuario(
        self,
        usuario_id: int,
        expediente_id: int | None = None,
        estado: str | None = None,
    ) -> list[ChatPrivado]:
        """Lista chats del usuario, opcionalmente filtrados por expediente/estado."""
        ...

    async def actualizar_estado(
        self, chat_id: int, propietario_id: int, estado: str
    ) -> ChatPrivado | None:
        """Cambia el estado (activo/archivado/eliminado). Devuelve chat actualizado."""
        ...

    async def actualizar_ultimo_mensaje_at(
        self, chat_id: int, propietario_id: int
    ) -> ChatPrivado | None:
        """Marca Timestamp del último mensaje. Devuelve chat actualizado."""
        ...
