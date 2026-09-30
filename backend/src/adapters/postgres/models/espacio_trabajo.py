"""Modelo SQLAlchemy de la tabla `espacio_trabajo`.

Espacio de trabajo privado de un usuario dentro de un expediente.
Equivalente adaptado de `chat_folders` de yampara_db.
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


class EspacioTrabajoModel(Base):
    """Modelo ORM de la tabla `espacio_trabajo`."""

    __tablename__ = "espacio_trabajo"

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
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'personalizado'"),
    )
    estado: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'activo'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "length(trim(nombre)) > 0",
            name="espacio_trabajo_valid_nombre",
        ),
        CheckConstraint(
            "tipo IN ('fijado', 'archivado', 'personalizado')",
            name="espacio_trabajo_tipo_check",
        ),
        CheckConstraint(
            "estado IN ('activo', 'eliminado')",
            name="espacio_trabajo_estado_check",
        ),
        Index(
            "espacio_trabajo_expediente_propietario_idx",
            "expediente_id",
            "propietario_id",
        ),
        Index("espacio_trabajo_estado_idx", "estado"),
        Index(
            "espacio_trabajo_nombre_unico_activos",
            "expediente_id",
            "propietario_id",
            "nombre",
            unique=True,
            postgresql_where=text("estado = 'activo'"),
        ),
    )
