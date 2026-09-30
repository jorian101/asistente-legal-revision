"""Modelo SQLAlchemy de la tabla `obra`.

Mapea la entidad de dominio `Obra` a la tabla `obra` en PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `obra`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- expediente_id BIGINT NOT NULL REFERENCES expediente(id) ON DELETE CASCADE
- propietario_id BIGINT NOT NULL REFERENCES usuario(id)
- tipo_documento TEXT NOT NULL CHECK (18 valores, ver constraint)
- corpus TEXT NULL CHECK (jurisprudencia|doctrina) + corpus_ref TEXT NULL
  (puntero N2/N3: abreviatura norma; NULL = pieza propia)
- estado_visibilidad TEXT NOT NULL DEFAULT 'privado' CHECK (2 valores)
- fuente TEXT NOT NULL DEFAULT 'carga_usuario' CHECK (2 valores)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indices:
- obra_expediente_id_idx (FK)
- obra_propietario_id_idx (FK)
- obra_expediente_propietario_idx (expediente_id, propietario_id) compuesto
- obra_publicadas_idx (expediente_id) WHERE estado_visibilidad = 'publicado' (parcial)
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
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ObraModel(Base):
    """Modelo ORM de la tabla `obra`."""

    __tablename__ = "obra"

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
    propietario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id"),
        nullable=False,
        index=True,
    )
    tipo_documento: Mapped[str] = mapped_column(String, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String, nullable=False)
    contenido_texto: Mapped[str] = mapped_column(String, nullable=False)
    estado_visibilidad: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'privado'")
    )
    fuente: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'carga_usuario'")
    )
    ruta_archivo: Mapped[str | None] = mapped_column(String, nullable=True)
    fojas_inicio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fojas_fin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tamano_archivo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estado_procesamiento: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'completado'"),
    )
    autor_instancia: Mapped[str | None] = mapped_column(String, nullable=True)
    # --- Campos de doctrina (Plan A) ---
    autor: Mapped[str | None] = mapped_column(String, nullable=True)
    fecha_documento: Mapped[str | None] = mapped_column(String, nullable=True)
    procedencia: Mapped[str | None] = mapped_column(String, nullable=True)
    estado_validacion: Mapped[str | None] = mapped_column(String, nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(String, nullable=True)
    recomendada: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    # --- Puntero a corpus N2/N3 (F3.2, niveles-corpus) ---
    corpus: Mapped[str | None] = mapped_column(String, nullable=True)
    corpus_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    # --- Soft delete (Plan A4) ---
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "tipo_documento IN ("
            "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
            "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
            "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
            "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro', "
            "'doctrina_libro', 'jurisprudencia', 'ejemplo', 'material_caso', 'norma_corpus'"
            ")",
            name="obra_tipo_documento_check",
        ),
        CheckConstraint(
            "corpus IS NULL OR corpus IN ('jurisprudencia', 'doctrina', 'norma')",
            name="obra_corpus_check",
        ),
        CheckConstraint(
            "estado_visibilidad IN ('privado', 'publicado', 'global', 'rechazado')",
            name="obra_estado_visibilidad_check",
        ),
        CheckConstraint(
            "fuente IN ('carga_usuario', 'generado_sistema')",
            name="obra_fuente_check",
        ),
        CheckConstraint(
            "estado_procesamiento IN ('pendiente', 'procesando', 'completado', 'fallido')",
            name="obra_estado_procesamiento_check",
        ),
        Index(
            "obra_expediente_propietario_idx",
            "expediente_id",
            "propietario_id",
        ),
        Index(
            "obra_publicadas_idx",
            "expediente_id",
            postgresql_where=text("estado_visibilidad = 'publicado'"),
        ),
        Index("obra_corpus_idx", "corpus", postgresql_where=text("corpus IS NOT NULL")),
        Index("obra_corpus_ref_idx", "corpus_ref", postgresql_where=text("corpus_ref IS NOT NULL")),
    )
