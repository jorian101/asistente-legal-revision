"""Modelo SQLAlchemy de la tabla `configuracion_rag`.

Mapea la configuracion RAG (singleton) a PostgreSQL.

Esquema exacto (arquitectura.md seccion 3.1, tabla `configuracion_rag`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- score_threshold NUMERIC(3,2) NOT NULL DEFAULT 0.75
- top_k_denso INTEGER NOT NULL DEFAULT 40
- top_k_lexico INTEGER NOT NULL DEFAULT 20
- top_k_final INTEGER NOT NULL DEFAULT 7
- modelo_embeddings TEXT NOT NULL DEFAULT 'nomic-embed-text'
- modelo_llm_default TEXT NOT NULL DEFAULT 'llama3:8b'
- actualizado_por BIGINT NULL REFERENCES usuario(id)
- updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Singleton: una sola fila activa. Solo el Administrador la modifica (HU-23).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ConfiguracionRAGModel(Base):
    """Modelo ORM de la tabla `configuracion_rag`."""

    __tablename__ = "configuracion_rag"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    score_threshold: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0.75")
    )
    top_k_denso: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("40"))
    top_k_lexico: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    top_k_final: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("7"))
    modelo_embeddings: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'nomic-embed-text'")
    )
    modelo_llm_default: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'llama3:8b'")
    )
    actualizado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    # Sprint 5 — ExpansorJerarquico.
    max_profundidad_bfs: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    top_k_padres_a_incluir: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    # Sprint 6 — LLM.
    temperatura: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.1"))
    # Sprint 3/Refactor - Reranker dynamic.
    reranker_endpoint_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Sprint 6 - LLM dynamic (seleccion admin).
    llm_endpoint_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Capa A (bug sala) - Normalizacion de query antes del embedding.
    # True por default; desactivable por admin (PUT
    # /admin/corpus/configuracion-rag/normalizar-query).
    normalizar_query: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
