"""Modelo SQLAlchemy de la tabla `borrador`.

Mapea la entidad de dominio `Borrador` a la tabla `borrador` en PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `borrador`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- expediente_id BIGINT NOT NULL REFERENCES expediente(id) ON DELETE CASCADE
- propietario_id BIGINT NOT NULL REFERENCES usuario(id)
- tipo TEXT NOT NULL CHECK (4 valores)
- estado TEXT NOT NULL DEFAULT 'borrador' CHECK (4 valores:
  borrador/publicado/pendiente_oficial/oficial)
- contexto_recuperado JSONB  (nullable)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
- updated_at TIMESTAMPTZ  (nullable)

Indices:
- borrador_expediente_id_idx (FK)
- borrador_propietario_id_idx (FK)
- borrador_expediente_propietario_idx (expediente_id, propietario_id) compuesto
- borrador_publicados_idx (expediente_id) WHERE estado = 'publicado' (parcial)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class BorradorModel(Base):
    """Modelo ORM de la tabla `borrador`."""

    __tablename__ = "borrador"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    expediente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    propietario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'borrador'"))
    contenido: Mapped[str] = mapped_column(String, nullable=False)
    plantilla_usada: Mapped[str | None] = mapped_column(String, nullable=True)
    contexto_recuperado: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    layout: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    razonamiento: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chat_privado.id", ondelete="SET NULL"),
        nullable=True,
    )
    mensaje_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("mensaje_chat.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "tipo IN ("
            "'dictamen_radicatoria', 'proyecto_auto_vista_consulta', "
            "'proyecto_auto_vista_apelacion', 'sugerencia_argumentacion'"
            ")",
            name="borrador_tipo_check",
        ),
        CheckConstraint(
            "estado IN ('borrador', 'publicado', 'pendiente_oficial', 'oficial')",
            name="borrador_estado_check",
        ),
        Index(
            "borrador_expediente_propietario_idx",
            "expediente_id",
            "propietario_id",
        ),
        Index(
            "borrador_publicados_idx",
            "expediente_id",
            postgresql_where=text("estado = 'publicado'"),
        ),
        Index("borrador_chat_idx", "chat_id"),
        Index("ix_borrador_activo", "expediente_id", postgresql_where=text("activo = true")),
    )
