"""Modelo SQLAlchemy de la tabla `fragmento`.

Mapea la entidad de dominio `Fragmento` a la tabla `fragmento` en PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `fragmento`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- norma_id BIGINT NULL REFERENCES norma(id) ON DELETE CASCADE
- obra_id BIGINT NULL REFERENCES obra(id) ON DELETE CASCADE
- expediente_id BIGINT NULL REFERENCES expediente(id) ON DELETE CASCADE
- qdrant_point_id TEXT NOT NULL                 (UUIDv4; '' = no indexable)
- texto TEXT NOT NULL
- padre_ref_id BIGINT NULL REFERENCES fragmento(id)        (self-ref)
- padre_ref_key TEXT NULL                                  (string semantico para Qdrant)
- nivel_jerarquico INT NULL CHECK (0..4)
- metadatos JSONB NULL                                    (incluye tipo_chunk)

Indices:
- fragmento_norma_id_idx (FK)
- fragmento_obra_id_idx (FK)
- fragmento_expediente_id_idx (FK)
- fragmento_padre_ref_id_idx (FK self-ref)
- UNIQUE parcial (qdrant_point_id) WHERE <> '' (estructurales comparten '')

Constraint:
- CHECK (num_nonnulls(norma_id, obra_id) = 1)  -- de una norma O de una obra
- CHECK (nivel_jerarquico BETWEEN 0 AND 4) IF NOT NULL
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class FragmentoModel(Base):
    """Modelo ORM de la tabla `fragmento`."""

    __tablename__ = "fragmento"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    norma_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("norma.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    obra_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("obra.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    expediente_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    padre_ref_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fragmento.id"),
        nullable=True,
        index=True,
    )
    padre_ref_key: Mapped[str | None] = mapped_column(String, nullable=True)
    nivel_jerarquico: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadatos: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(norma_id, obra_id) = 1",
            name="fragmento_norma_or_obra_check",
        ),
        CheckConstraint(
            "(nivel_jerarquico IS NULL) OR (nivel_jerarquico BETWEEN 0 AND 4)",
            name="fragmento_nivel_jerarquico_check",
        ),
        # Los estructurales comparten '' como qdrant_point_id: unico solo si no es ''.
        Index(
            "uq_fragmento_qdrant_point_id",
            "qdrant_point_id",
            unique=True,
            postgresql_where=text("qdrant_point_id <> ''"),
        ),
    )
