"""Adapter: PyJwtService — Servicio de tokens JWT (HS256).

Implementa JwtService (Protocol) usando PyJWT. Access token 1h HS256 con
payload {sub: str(usuario_id), rol: str, exp: int}. Refresh token es un
string aleatorio opaco (no JWT) de 32 bytes; en BD se almacena su SHA-256.

Regla 2 Trail of Bits:
- access token: corta vida (1h) en memoria JS frontend. NO httpOnly (el
  frontend lo necesita para Authorization header).
- refresh token: larga vida (7d) en cookie httpOnly/Secure/SameSite=Strict.
  El frontend nunca lo lee. Solo el backend lo manipula.

Sprint 1 Auth, plan v3, decision D5: PyJWT (no python-jose). El secret es
Settings.secret_key (env SECRET_KEY) — suficiente para HS256 single-instance.

Nota sobre verificacion de rol: NO confiamos solo en el claim `rol` del JWT.
El dependency `require_admin` re-verifica el rol contra BD en cada request
sensible — el JWT solo evita el lookup en cada endpoint.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt

from src.config import get_settings

_ALGORITHM = "HS256"
_ACCESS_TTL = timedelta(hours=1)
_REFRESH_BYTES = 32  # 256 bits opaco


class PyJwtService:
    """Implementacion concreta de JwtService con PyJWT."""

    def __init__(self, secret: str | None = None) -> None:
        # Inyeccion para tests; por defecto toma SECRET_KEY del env.
        self._secret = secret if secret is not None else get_settings().secret_key

    def crear_access_token(self, usuario_id: int, rol: str) -> str:
        ahora = datetime.now(UTC)
        payload = {
            "sub": str(usuario_id),
            "rol": rol,
            "iat": ahora,
            "exp": ahora + _ACCESS_TTL,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def crear_refresh_token(self) -> str:
        return secrets.token_urlsafe(_REFRESH_BYTES)

    def verificar_access_token(self, token: str) -> dict:
        return jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
