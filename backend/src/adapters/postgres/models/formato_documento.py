"""Modelo SQLAlchemy de la tabla `formato_documento`.

Mapea la entidad de dominio `FormatoDocumento` a PostgreSQL.
Tabla para el módulo formatos (pipeline alta fidelidad TSJM).

Esquema:
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- tipo_documento TEXT NOT NULL CHECK (14 valores de obra.TipoDocumento)
- slug TEXT NOT NULL UNIQUE
- autor TEXT NOT NULL CHECK (5 valores)
- engine TEXT NOT NULL
- estado TEXT NOT NULL CHECK (borrador/canonico)
- version INT NOT NULL DEFAULT 1
- meta JSONB
- bloques JSONB NOT NULL (lista de bloques layout.json)
- esqueleto JSONB (formato con template/texto_plantilla + placeholders, opcional)
- hash_fuente TEXT
- created_at / updated_at TIMESTAMPTZ
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class FormatoDocumentoModel(Base):
    """Modelo ORM de la tabla `formato_documento`."""

    __tablename__ = "formato_documento"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    tipo_documento: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    autor: Mapped[str] = mapped_column(String, nullable=False)
    engine: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'borrador'"))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bloques: Mapped[list] = mapped_column(JSONB, nullable=False)
    esqueleto: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    hash_fuente: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "tipo_documento IN ("
            "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
            "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
            "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
            "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro'"
            ")",
            name="formato_tipo_check",
        ),
        CheckConstraint(
            "autor IN ('aliaga', 'tsjm-otro', 'instancia-inferior', 'parte', 'desconocido')",
            name="formato_autor_check",
        ),
        CheckConstraint(
            "estado IN ('borrador', 'canonico')",
            name="formato_estado_check",
        ),
        Index("ix_formato_autor", "autor"),
        Index("ix_formato_estado", "estado"),
        Index("ix_formato_tipo", "tipo_documento"),
    )
