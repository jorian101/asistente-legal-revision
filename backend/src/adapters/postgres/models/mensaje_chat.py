"""Modelo SQLAlchemy de la tabla `mensaje_chat`.

Mensajes USER/BOT dentro de un chat privado.
Equivalente adaptado de `chat_messages` de yampara_db.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class MensajeChatModel(Base):
    """Modelo ORM de la tabla `mensaje_chat`."""

    __tablename__ = "mensaje_chat"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_privado.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    razonamiento: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    contenido: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'activo'"),
    )
    posicion: Mapped[int] = mapped_column(Integer, nullable=False)
    metadatos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('user', 'bot')",
            name="mensaje_chat_tipo_check",
        ),
        CheckConstraint(
            "length(trim(contenido)) > 0",
            name="mensaje_chat_valid_contenido",
        ),
        CheckConstraint(
            "estado IN ('activo', 'editado', 'eliminado')",
            name="mensaje_chat_estado_check",
        ),
        Index(
            "mensaje_chat_chat_posicion_idx",
            "chat_id",
            "posicion",
        ),
        Index("mensaje_chat_estado_idx", "estado"),
        Index(
            "mensaje_chat_posicion_unico_visibles",
            "chat_id",
            "posicion",
            unique=True,
            postgresql_where=text("estado IN ('activo', 'editado')"),
        ),
    )
