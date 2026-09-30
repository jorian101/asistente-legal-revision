"""Port: EmailService — Envío de emails transaccionales (2FA, notificaciones).

Fase 2 plan jurado. Protocol — structural typing, implementaciones no necesitan heredar.
Clean Architecture: use cases dependen de este puerto; la implementación
vive en adapters/.
"""

from __future__ import annotations

from typing import Protocol


class EmailService(Protocol):
    """Servicio de envío de emails transaccionales."""

    async def enviar_codigo_2fa(self, email: str, codigo: str, ttl_minutes: int) -> None:
        """Envía código 2FA de 6 dígitos a email.
        Sin configuración (dev mode) el adapter falla con error claro; el código
        nunca se loguea.
        """
        ...

    async def enviar_email_generico(
        self, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        """Envío genérico para futuras notificaciones."""
        ...
