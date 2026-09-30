"""Use case: Refresh de token de acceso.

Sprint 1 Auth (plan v3). Recibe DI de AuthRepository + JwtService.

Regla 2 Trail of Bits:
1. SHA-256 del refresh token recibido
2. lookup en BD — si no existe o revocado: REPLAY -> revocar todos + 401
3. verificar no expirado
4. revocar token actual (rotacion)
5. generar nuevo refresh + nuevo access (con el rol real del usuario)
6. guardar SHA-256 del nuevo refresh en BD
7. retornar (access_token, refresh_token)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository
    from src.application.ports.jwt_service import JwtService


class RefreshTokenError(Exception):
    """Token invalido, revocado o expirado."""


class ReplayError(RefreshTokenError):
    """Token ya usado (replay attack) — todos los tokens del usuario revocados."""


@dataclass
class RefreshResponse:
    access_token: str
    refresh_token: str


async def execute(
    refresh_token: str,
    auth_repo: AuthRepository,
    jwt_service: JwtService,
) -> RefreshResponse:
    """Valida refresh token y rota.

    Args:
        refresh_token: token opaco recibido del cliente (raw, cookie).
        auth_repo: AuthRepository.
        jwt_service: JwtService.

    Returns:
        RefreshResponse con nuevo par de tokens.

    Raises:
        RefreshTokenError: token invalido, expirado o no encontrado.
        ReplayError: reuso de token revocado — todos los tokens revocados.
    """
    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    record = await auth_repo.get_refresh_token(token_hash)

    if record is None:
        raise RefreshTokenError

    if record.revocado:
        await auth_repo.revocar_todos_refresh_tokens(record.usuario_id)
        raise ReplayError

    ahora = datetime.now(record.created_at.tzinfo or UTC)
    if ahora > record.expires_at:
        await auth_repo.revocar_refresh_token(token_hash)
        raise RefreshTokenError

    usuario = await auth_repo.get_by_id(record.usuario_id)
    if usuario is None or not usuario.activo:
        await auth_repo.revocar_refresh_token(token_hash)
        raise RefreshTokenError

    await auth_repo.revocar_refresh_token(token_hash)
    new_refresh = jwt_service.crear_refresh_token()
    new_hash = hashlib.sha256(new_refresh.encode("utf-8")).hexdigest()
    exp_nueva = ahora + timedelta(days=7)
    await auth_repo.guardar_refresh_token(record.usuario_id, new_hash, exp_nueva)

    access_token = jwt_service.crear_access_token(record.usuario_id, str(usuario.rol))

    return RefreshResponse(access_token=access_token, refresh_token=new_refresh)
