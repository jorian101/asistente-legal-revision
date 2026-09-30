"""Modelo SQLAlchemy de la tabla `usuario_modulo_permiso`.

Overrides de permisos CRUD de un usuario sobre un módulo. La matriz DEFAULT
del rol vive en código (domain/entities/permiso.py: DEFAULTS_POR_ROL); esta
tabla solo guarda las excepciones que el admin asigna por usuario.

Semántica de los flags (nullable):
- NULL = sin override → seguir el default del rol.
- TRUE/FALSE = override explícito que anula el default.

Esquema:
- usuario_id BIGINT FK usuario.id ON DELETE CASCADE
- modulo_id BIGINT FK modulo.id ON DELETE CASCADE
- puede_crear BOOLEAN NULL
- puede_leer BOOLEAN NULL
- puede_actualizar BOOLEAN NULL
- puede_eliminar BOOLEAN NULL
- PK compuesta (usuario_id, modulo_id) — un solo override por par

Índices: usuario_id (consulta de permisos por usuario), modulo_id.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class UsuarioModuloPermisoModel(Base):
    """Modelo ORM de la tabla `usuario_modulo_permiso`."""

    __tablename__ = "usuario_modulo_permiso"

    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    modulo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("modulo.id", ondelete="CASCADE"), nullable=False
    )
    puede_crear: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    puede_leer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    puede_actualizar: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    puede_eliminar: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("usuario_id", "modulo_id"),
        Index("usuario_modulo_permiso_usuario_idx", "usuario_id"),
        Index("usuario_modulo_permiso_modulo_idx", "modulo_id"),
    )
