"""Port: JwtService — Servicio de tokens JWT para autenticacion.

Sprint 1 Auth (plan v3, decision D5: PyJWT HS256). Protocol — structural typing.

Regla 2 Trail of Bits:
- access token 1h HS256 (memoria React frontend)
- refresh token opaco 7d (cookie httpOnly/Secure/SameSite=Strict)
- verificacion NO confia solo en claim del JWT — rol se re-verifica contra BD
"""

from __future__ import annotations

from typing import Protocol


class JwtService(Protocol):
    """Servicio de tokens JWT. Implementado por PyJwtService."""

    def crear_access_token(self, usuario_id: int, rol: str) -> str:
        """Genera access token con payload {sub: str(id), rol, exp}. 1h HS256."""
        ...

    def crear_refresh_token(self) -> str:
        """Genera token opaco aleatorio (no JWT). Se almacena SHA-256 en BD."""
        ...

    def verificar_access_token(self, token: str) -> dict:
        """Decodifica y valida access token. Retorna payload: {sub, rol, exp}.

        Raises: jwt.ExpiredSignatureError, jwt.InvalidTokenError.
        """
        ...
