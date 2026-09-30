"""Modelo SQLAlchemy de la tabla `norma`.

Mapea la entidad de dominio `Norma` a la tabla `norma` en PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `norma`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- abreviatura TEXT NOT NULL UNIQUE
- tipo TEXT NOT NULL CHECK (7 valores)
- jerarquia TEXT NOT NULL CHECK (5 valores)
- version TEXT NULL
- ruta_archivo TEXT NULL
- indexado BOOLEAN NOT NULL DEFAULT false
- indexado_por BIGINT NULL REFERENCES usuario(id)
- origen_obra_id BIGINT NULL REFERENCES obra(id) ON DELETE SET NULL (promoción)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indices:
- UNIQUE(abreviatura)
- norma_indexado_idx (boolean)
- norma_tipo_jerarquia_idx (tipo, jerarquia) — compuesto

Naming: tabla singular snake_case. CHECK en vez de ENUMs (regla arquitectura
md seccion 3.1).
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class NormaModel(Base):
    """Modelo ORM de la tabla `norma`."""

    __tablename__ = "norma"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    abreviatura: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    jerarquia: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    ruta_archivo: Mapped[str | None] = mapped_column(String, nullable=True)
    indexado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    indexado_por: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=True,
        index=True,
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    propietario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True
    )
    estado_visibilidad: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'global'"), index=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(String, nullable=True)
    # Obra desde la que se promovió esta norma (jurisprudencia/norma promovida).
    origen_obra_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("obra.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "tipo IN ("
            "'constitucion', 'codigo_militar', 'codigo_ordinario', "
            "'ley_organica', 'reglamento', 'scp_tcp', 'sentencia_cidh', "
            "'doctrina_libro'"
            ")",
            name="norma_tipo_check",
        ),
        CheckConstraint(
            "jerarquia IN ('suprema', 'militar', 'supletoria', 'jurisprudencia', 'doctrina')",
            name="norma_jerarquia_check",
        ),
        CheckConstraint(
            "estado_visibilidad IN ('privado', 'pendiente', 'global', 'rechazado')",
            name="norma_estado_visibilidad_check",
        ),
        Index("norma_indexado_idx", "indexado"),
        Index("norma_tipo_jerarquia_idx", "tipo", "jerarquia"),
        Index("ix_norma_abreviatura", "abreviatura"),
        Index("ix_norma_activo", "abreviatura", postgresql_where=text("activo = true")),
        Index(
            "norma_origen_obra_idx",
            "origen_obra_id",
            postgresql_where=text("origen_obra_id IS NOT NULL"),
        ),
    )
