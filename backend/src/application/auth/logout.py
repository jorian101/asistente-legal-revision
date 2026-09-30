"""Use case: Logout (revocar refresh token).

Sprint 1 Auth (plan v3). Revoca el refresh token actual para que no pueda
usarse nuevamente. El access token sigue valido hasta su expiracion (1h),
el frontend lo descarta de memoria.

Regla 2 Trail of Bits: rotacion — cada logout invalida el refresh.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository


async def execute(refresh_token: str, auth_repo: AuthRepository) -> None:
    """Revoca un refresh token.

    Args:
        refresh_token: token opaco recibido del cliente (raw, header).
        auth_repo: AuthRepository.
    """
    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    await auth_repo.revocar_refresh_token(token_hash)
