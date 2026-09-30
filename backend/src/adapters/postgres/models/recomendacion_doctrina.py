"""Modelo SQLAlchemy de la tabla `recomendacion_doctrina`.

Recomendación de una doctrina GLOBAL a un expediente específico (Plan
expedientes compartidos + recomendación). Supervisor auto-aprueba su
recomendación; operador propone y el supervisor aprueba/rechaza.

Esquema:
- id BIGINT PK IDENTITY
- obra_global_id BIGINT NOT NULL FK obra (la doctrina global)
- expediente_id BIGINT NOT NULL FK expediente
- recomendado_por BIGINT NOT NULL FK usuario (quien recomienda)
- estado TEXT NOT NULL DEFAULT 'pendiente' ('recomendada'|'pendiente'|'rechazada')
- aprobado_por BIGINT NULL FK usuario (supervisor que aprobó/rechazó)
- motivo_rechazo TEXT NULL
- created_at / updated_at TIMESTAMPTZ
- UNIQUE(obra_global_id, expediente_id)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class RecomendacionDoctrinaModel(Base):
    """Modelo ORM de la tabla `recomendacion_doctrina`."""

    __tablename__ = "recomendacion_doctrina"
    __table_args__ = (
        UniqueConstraint(
            "obra_global_id",
            "expediente_id",
            name="uq_recomendacion_obra_expediente",
        ),
        Index("ix_recomendacion_expediente", "expediente_id"),
        Index(
            "uq_recomendacion_corpus_expediente",
            "expediente_id",
            "corpus",
            "corpus_ref",
            unique=True,
            postgresql_where=text("obra_global_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    obra_global_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("obra.id", ondelete="CASCADE"), nullable=True
    )
    corpus: Mapped[str | None] = mapped_column(String, nullable=True)
    corpus_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    expediente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expediente.id", ondelete="CASCADE"), nullable=False
    )
    recomendado_por: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False
    )
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pendiente'"))
    aprobado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
