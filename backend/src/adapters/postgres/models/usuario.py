"""Modelo SQLAlchemy de la tabla `usuario`.

Mapea la entidad de dominio `Usuario` a la tabla `usuario` en PostgreSQL.
El mapeo entidad ORM <-> entidad dominio lo hace el repositorio
SqlUsuarioRepo (en este mismo adapter). Este modulo solo declara el schema.

Esquema exacto (arquitectura.md seccion 3.1, tabla `usuario`):
- PK BIGINT GENERATED ALWAYS AS IDENTITY
- carnet TEXT NOT NULL UNIQUE (CI o CM alfanumerico; Sprint 1 plan v3 D1)
- rol TEXT NOT NULL CHECK (rol IN ('administrador', 'supervisor', 'operador_juridico'))
- cargo TEXT NOT NULL
- activo BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
- email TEXT NULL (compartido permitido: varios usuarios pueden usar el mismo)
- email_verificado BOOLEAN NOT NULL DEFAULT false
- codigo_2fa_hash TEXT NULL
- codigo_2fa_expira TIMESTAMPTZ NULL
- intentos_codigo INTEGER NOT NULL DEFAULT 0
- bloqueado_hasta TIMESTAMPTZ NULL

Naming: tabla singular snake_case (ver arquitectura.md). En vez de ENUM de PG
usamos CHECK constraint (regla arquitectura.md seccion 3.1).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class UsuarioModel(Base):
    """Modelo ORM de la tabla `usuario`."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    carnet: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    rol: Mapped[str] = mapped_column(String, nullable=False)
    cargo: Mapped[str] = mapped_column(String, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email_verificado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    codigo_2fa_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    codigo_2fa_expira: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    intentos_codigo: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "rol IN ('administrador', 'supervisor', 'operador_juridico')",
            name="usuario_rol_check",
        ),
        CheckConstraint(
            "cargo IN ('Auditor', 'Fiscal', 'Vocal Relator', 'Secretaria de Cámara', "
            "'Vocal Presidente', 'Auxiliar de Secretaría de Cámara', 'Personal Técnico')",
            name="usuario_cargo_check",
        ),
    )
