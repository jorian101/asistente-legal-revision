"""Modelo SQLAlchemy de la tabla `obra_origen` (Plan A).

Trazabilidad: cuando un operador selecciona una doctrina global y se copia a
su expediente (o a la consulta sin expediente), se registra de qué obra
global vino, quién la copió y cuándo.

Esquema:
- id BIGINT PK GENERATED ALWAYS AS IDENTITY
- obra_id BIGINT NOT NULL REFERENCES obra(id) ON DELETE CASCADE  (la copia)
- obra_origen_id BIGINT NOT NULL REFERENCES obra(id) ON DELETE CASCADE  (la global)
- copiada_por BIGINT NOT NULL REFERENCES usuario(id)
- copiada_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
- sin_expediente BOOLEAN NOT NULL DEFAULT FALSE (copia a consulta sin expediente)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ObraOrigenModel(Base):
    """Modelo ORM de la tabla `obra_origen`."""

    __tablename__ = "obra_origen"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    obra_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("obra.id", ondelete="CASCADE"), nullable=False
    )
    obra_origen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("obra.id", ondelete="CASCADE"), nullable=False
    )
    copiada_por: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuario.id"), nullable=False)
    copiada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    sin_expediente: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
