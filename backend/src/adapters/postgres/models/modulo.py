"""Modelo SQLAlchemy de la tabla `modulo`.

Catálogo fijo de módulos del sistema (permisos CRUD por usuario).
Se siembra por migración Alembic con los 11 módulos actuales; el admin solo
edita nombre/descripcion/ruta/orden/activo, no crea claves nuevas.

Esquema:
- id BIGINT PK GENERATED ALWAYS AS IDENTITY
- clave TEXT NOT NULL UNIQUE (slug, ej. 'usuarios', 'corpus', 'consultar')
- nombre TEXT NOT NULL (legible para UI)
- descripcion TEXT NOT NULL DEFAULT ''
- ruta TEXT NOT NULL (ruta frontend del módulo)
- orden INTEGER NOT NULL DEFAULT 0 (posición en sidebar)
- activo BOOLEAN NOT NULL DEFAULT true
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class ModuloModel(Base):
    """Modelo ORM de la tabla `modulo`."""

    __tablename__ = "modulo"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=text("GENERATED ALWAYS AS IDENTITY"),
    )
    clave: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    descripcion: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    ruta: Mapped[str] = mapped_column(String, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
