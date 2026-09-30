"""Modelo SQLAlchemy de la tabla `audit_log`.

Trail of Bits Regla R6 (trazabilidad de acciones sensitivas):
registra QUÉ hizo QUIÉN, sobre QUÉ entidad, CUÁNDO y desde DÓNDE.
Append-only en escritura (no UPDATE/DELETE); limpieza por politica de
retencion fuera de esta migracion.

Esquema:
- id BIGINT PK GENERATED ALWAYS AS IDENTITY
- accion TEXT NOT NULL (ej. 'login', 'crear_expediente', 'publicar_borrador')
- entidad TEXT NULL (ej. 'expediente', 'borrador', 'usuario')
- entidad_id BIGINT NULL
- usuario_id BIGINT NULL REFERENCES usuario(id)
- detalle JSONB NULL (contexto opcional: ip, carnet, extra)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indices: accion+created_at para queries por tipo de accion; usuario_id.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class AuditLogModel(Base):
    """Modelo ORM de la tabla `audit_log`."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    accion: Mapped[str] = mapped_column(Text, nullable=False)
    entidad: Mapped[str | None] = mapped_column(Text, nullable=True)
    entidad_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    detalle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("audit_log_accion_created_at_idx", "accion", "created_at"),
        Index("audit_log_usuario_idx", "usuario_id"),
    )
