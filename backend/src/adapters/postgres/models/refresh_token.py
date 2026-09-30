"""Modelo SQLAlchemy de la tabla `refresh_token`.

Soporta Regla 2 Trail of Bits:
- rotacion: cada refresh invalida el anterior (revocado=true)
- replay detection: si un token revocado se reusa -> revocar TODOS los del usuario
- expiracion 7 dias

Almacenamos SHA-256(token opaco) en `token_hash` (nunca el raw). Lookup por
hash es O(1) via ix_refresh_token_token_hash (unique). El token raw solo vive
en cookie httpOnly del cliente.

Sprint 1 Auth, Migracion M2 (d8afe037caab).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.postgres.base import Base


class RefreshTokenModel(Base):
    """Modelo ORM de la tabla `refresh_token`."""

    __tablename__ = "refresh_token"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
