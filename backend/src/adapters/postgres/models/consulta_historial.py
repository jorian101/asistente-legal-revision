"""Modelo SQLAlchemy de la tabla `consulta_historial`.

Mapea el historial de consultas RAG a PostgreSQL.

Esquema (arquitectura.md seccion 3.1, tabla `consulta_historial` + decision D11):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- expediente_id BIGINT NULL REFERENCES expediente(id) ON DELETE CASCADE
  (NULL: una consulta_simple no requiere expediente — decision D11)
- usuario_id BIGINT NOT NULL REFERENCES usuario(id)
- pregunta TEXT NOT NULL
- respuesta TEXT NULL (NULL en Sprint 3; la respuesta LLM llega en Sprint 6 — D11)
- tipo_respuesta TEXT NULL (D11: consulta_simple | auto_vista_consulta | ...)
- fuentes_recuperadas JSONB NULL (ContextoRecuperado serializado)
- latencia_ms INTEGER NULL
- modelo_llm TEXT NULL
- estado TEXT NOT NULL DEFAULT 'en_progreso' (migracion 0f1a2b3c4d5e:
  en_progreso | completado | error — Sala de Control deja de inferir el
  estado a partir de respuesta/tipo_respuesta NULL)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indices:
- consulta_historial_expediente_usuario_idx (expediente_id, usuario_id)
- consulta_historial_created_at_idx (created_at DESC)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
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


class ConsultaHistorialModel(Base):
    """Modelo ORM de la tabla `consulta_historial`."""

    __tablename__ = "consulta_historial"

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
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False, index=True
    )
    pregunta: Mapped[str] = mapped_column(Text, nullable=False)
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_respuesta: Mapped[str | None] = mapped_column(String, nullable=True)
    fuentes_recuperadas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo_llm: Mapped[str | None] = mapped_column(String, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'en_progreso'")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("consulta_historial_expediente_usuario_idx", "expediente_id", "usuario_id"),
        Index("consulta_historial_created_at_idx", "created_at"),
        Index(
            "ix_consulta_historial_activo",
            "usuario_id",
            text("created_at DESC"),
            postgresql_where=text("activo = true"),
        ),
    )
