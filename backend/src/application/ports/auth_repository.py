"""Port: AuthRepository — Repositorio de autenticacion (usuario, refresh_token, intentos_login).

Sprint 1 Auth (plan v3). Protocol — structural typing, implementaciones no necesitan heredar.
Regla Clean Architecture: este port define la interfaz abstracta. La implementacion
SqlAuthRepository vive en adapters/postgres/ y conoce SQLAlchemy. Los use cases
solo dependen de este protocolo.

Soporta Regla 2 Trail of Bits:
- refund token rotation (guardar, revocar, revocar_todos)
- detection de replay (get_refresh_token + revocar_todos al detectar reuse)
- rate limit + lockout (registrar_intento, contar_intentos_fallidos, contar_intentos_por_ip)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.entities.usuario import Usuario


@dataclass
class RefreshTokenData:
    """DTO: fila de tabla refresh_token (dominio puro, sin ORM)."""

    id: str
    usuario_id: int
    token_hash: str
    expires_at: datetime
    revocado: bool
    created_at: datetime


class AuthRepository(Protocol):
    """Repositorio de autenticacion. Implementado por SqlAuthRepository."""

    async def get_by_carnet(self, carnet: str) -> Usuario | None:
        """Busca usuario por carnet (CI/CM). Retorna Usuario o None."""
        ...

    async def get_by_id(self, usuario_id: int) -> Usuario | None:
        """Busca usuario por PK. Usado por dependencia get_current_user."""
        ...

    async def crear_usuario(self, usuario: Usuario) -> Usuario:
        """Inserta un usuario nuevo en BD. Retorna usuario con ID asignado."""
        ...

    async def actualizar_usuario(
        self, usuario: Usuario, carnet_original: str | None = None
    ) -> Usuario:
        """Actualiza un usuario. `carnet_original` identifica la fila cuando el
        carnet del usuario cambia; si es None se usa `usuario.carnet`."""
        ...

    async def listar_usuarios(self) -> list[Usuario]:
        """Lista todos los usuarios ordenados por carnet (asc)."""
        ...

    async def guardar_refresh_token(
        self, usuario_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Almacena hash SHA-256 de un refresh token recien emitido."""
        ...

    async def revocar_refresh_token(self, token_hash: str) -> None:
        """Marca un token como revocado (rotacion)."""
        ...

    async def revocar_todos_refresh_tokens(self, usuario_id: int) -> None:
        """Replay detection: revoca TODOS los refresh tokens del usuario."""
        ...

    async def get_refresh_token(self, token_hash: str) -> RefreshTokenData | None:
        """Busca refresh token por hash (unique index). Usado para verificacion RPLY."""
        ...

    async def registrar_intento(self, carnet: str, ip: str, exitoso: bool) -> None:
        """Registra intento de login en la tabla intentos_login."""
        ...

    async def contar_intentos_fallidos(self, carnet: str, desde: datetime) -> int:
        """Cuenta intentos fallidos por carnet en una ventana temporal (lockout)."""
        ...

    async def contar_intentos_por_ip(self, ip: str, desde: datetime) -> int:
        """Cuenta intentos desde una IP en ventana temporal (rate limit)."""
        ...

    async def actualizar_email(self, carnet: str, email: str) -> None:
        """Actualiza el email y lo deja pendiente de verificación."""
        ...

    async def marcar_email_verificado(self, carnet: str) -> None:
        """Marca el email del usuario como verificado."""
        ...

    async def guardar_codigo_2fa(self, carnet: str, codigo_hash: str, expira: datetime) -> None:
        """Guarda el hash y expiración del código 2FA, reiniciando intentos."""
        ...

    async def verificar_codigo_2fa(self, carnet: str, codigo_hash: str) -> bool:
        """Verifica hash y expiración del código sin exponer el código original."""
        ...

    async def incrementar_intentos_2fa(self, carnet: str) -> int:
        """Incrementa intentos y bloquea al alcanzar el límite configurado."""
        ...

    async def limpiar_codigo_2fa(self, carnet: str) -> None:
        """Limpia el código temporal y reinicia sus intentos."""
        ...

    async def desbloquear_2fa(self, carnet: str) -> None:
        """Desbloquea manualmente una cuenta 2FA."""
        ...
