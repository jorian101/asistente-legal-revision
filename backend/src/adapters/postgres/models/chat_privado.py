"""Modelo SQLAlchemy de la tabla `chat_privado`.

Conversación RAG persistente dentro de un expediente.
Equivalente adaptado de `chats` + `chat_sessions` de yampara_db.
Un usuario puede tener múltiples chats privados en un expediente.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ChatPrivadoModel(Base):
    """Modelo ORM de la tabla `chat_privado`."""

    __tablename__ = "chat_privado"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    expediente_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    espacio_trabajo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("espacio_trabajo.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    propietario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'activo'"),
    )
    prioridad: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'media'"),
    )
    contexto_legal: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_mensaje_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(titulo)) > 0",
            name="chat_privado_valid_titulo",
        ),
        CheckConstraint(
            "estado IN ('activo', 'archivado', 'eliminado')",
            name="chat_privado_estado_check",
        ),
        CheckConstraint(
            "prioridad IN ('baja', 'media', 'alta', 'critica')",
            name="chat_privado_prioridad_check",
        ),
        CheckConstraint(
            "contexto_legal IN ('caso_legal', 'audiencia', 'reunion', "
            "'antecedente', 'documento_legal', 'consulta_general')",
            name="chat_privado_contexto_legal_check",
        ),
        Index(
            "chat_privado_expediente_propietario_idx",
            "expediente_id",
            "propietario_id",
        ),
        Index("chat_privado_estado_idx", "estado"),
        Index("chat_privado_ultimo_mensaje_at_idx", "ultimo_mensaje_at"),
    )
