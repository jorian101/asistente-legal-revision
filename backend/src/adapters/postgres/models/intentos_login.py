"""Modelo SQLAlchemy de la tabla `intentos_login`.

Soporta Regla 2 Trail of Bits:
- rate limit 5 intentos/min por IP (query: WHERE ip=? AND timestamp>=?)
- lockout tras 10 fallidos por carnet en 1h (WHERE carnet=? AND exitoso=false AND timestamp>=?)

Tabla de log de auditoria: append-only en escritura, limpieza por politica
de retencion fuera de esta migracion. Indices compuestos cubren las 2 queries
del use case login.py sin escaneo completo.

Sprint 1 Auth, Migracion M3 (3f29ce1f4cba).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class IntentosLoginModel(Base):
    """Modelo ORM de la tabla `intentos_login`."""

    __tablename__ = "intentos_login"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    carnet: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("ix_intentos_login_carnet_timestamp", "carnet", "timestamp"),
        Index("ix_intentos_login_ip_timestamp", "ip", "timestamp"),
    )
