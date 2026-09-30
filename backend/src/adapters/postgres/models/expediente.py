"""Modelo SQLAlchemy de la tabla `expediente`.

Mapea la entidad de dominio `Expediente` a la tabla `expediente` en PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `expediente`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- numero_caso TEXT NOT NULL UNIQUE
- tipo_proceso TEXT NOT NULL CHECK (2 valores)
- estado TEXT NOT NULL DEFAULT 'activo' CHECK (2 valores)
- abierto_por BIGINT NOT NULL REFERENCES usuario(id)  (s/ondelete=<default RESTRICT>)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indices (arquitectura.md):
- expediente_estado_idx
- expediente_abierto_por_idx (FK)
- expediente_created_at_idx
- UNIQUE(numero_caso) implicito
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
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ExpedienteModel(Base):
    """Modelo ORM de la tabla `expediente`."""

    __tablename__ = "expediente"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    numero_caso: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    tipo_proceso: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'activo'"))
    tribunal_origen: Mapped[str] = mapped_column(String, nullable=False)
    procesado_nombre: Mapped[str] = mapped_column(String, nullable=False)
    delito: Mapped[str] = mapped_column(String, nullable=False)
    abierto_por: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    procesado_grado: Mapped[str | None] = mapped_column(String, nullable=True)
    sentencia_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    fojas_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "tipo_proceso IN ('consulta', 'apelacion_incidental', 'apelacion_restringida')",
            name="expediente_tipo_proceso_check",
        ),
        CheckConstraint(
            "estado IN ('activo', 'archivado')",
            name="expediente_estado_check",
        ),
        Index("expediente_estado_idx", "estado"),
        Index("expediente_created_at_idx", "created_at"),
    )
