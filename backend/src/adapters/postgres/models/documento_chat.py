"""Modelo SQLAlchemy de la tabla `documento_chat`.

Documentos adjuntos a mensajes del chat.
Equivalente adaptado de `chat_documents` de yampara_db.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class DocumentoChatModel(Base):
    """Modelo ORM de la tabla `documento_chat`."""

    __tablename__ = "documento_chat"

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
    mensaje_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mensaje_chat.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    nombre_original: Mapped[str] = mapped_column(String, nullable=False)
    tamano_archivo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String, nullable=False)
    estado_procesamiento: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'pendiente'"),
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(nombre_original)) > 0",
            name="documento_chat_valid_nombre",
        ),
        CheckConstraint(
            "tamano_archivo > 0",
            name="documento_chat_valid_tamano",
        ),
        CheckConstraint(
            "tipo_documento IN ('pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'json', "
            "'png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'tiff')",
            name="documento_chat_tipo_documento_check",
        ),
        CheckConstraint(
            "estado_procesamiento IN ('pendiente', 'procesando', 'completado', 'fallido')",
            name="documento_chat_estado_procesamiento_check",
        ),
    )
