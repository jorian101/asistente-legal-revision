"""Use case: Verificar código 2FA (carnet + código 6 dígitos -> JWT + refresh cookie).

Fase 2 plan jurado. Flujo:
1. Verificar lockout 2FA (bloqueado_hasta > now).
2. Verificar hash SHA-256 del código + no expirado (via verificar_codigo_2fa).
3. Si OK: limpiar código, resetear intentos, generar JWT + refresh, guardar hash.
4. Si fallo: incrementar intentos_2fa; si llega a 3 -> bloqueado_hasta=now+1h.
5. Retornar LoginResponse (access_token, refresh_token, rol, carnet, id).

Errores:
- Código inválido/expirado -> Verificar2FaError
- Lockout 2FA (3 intentos) -> Verificar2FaError (bloqueado, admin desbloquea)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from src.application.ports.auth_repository import AuthRepository
from src.application.ports.jwt_service import JwtService


class Verificar2FaError(Exception):
    """Error en verificación 2FA (código inválido, expirado, lockout)."""


@dataclass
class Verificar2FaResponse:
    access_token: str
    refresh_token: str
    rol: str
    carnet: str
    nombre: str
    id: int
    cargo: str


async def execute(
    carnet: str,
    codigo: str,
    ip: str,
    auth_repo: AuthRepository,
    jwt_service: JwtService,
) -> Verificar2FaResponse:
    """Ejecuta la verificación del código 2FA.

    Args:
        carnet: CI/CM del usuario.
        codigo: Código 6 dígitos en texto plano.
        ip: IP del cliente (rate limit reutiliza contar_intentos_por_ip).
        auth_repo: Repositorio de autenticación.
        jwt_service: Servicio JWT.

    Returns:
        Verificar2FaResponse con tokens y datos usuario.

    Raises:
        Verificar2FaError: código inválido, expirado, lockout 2FA.
    """
    ahora = datetime.now(UTC)

    # Rate limit 2FA: 3 códigos / 5 min por IP (mismo que solicitar)
    desde_5min = ahora - timedelta(minutes=5)
    intentos_ip = await auth_repo.contar_intentos_por_ip(ip, desde_5min)
    if intentos_ip >= 3:
        raise Verificar2FaError("Demasiados intentos. Aguarda 5 minutos.")

    # Verificar lockout 2FA
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None or not usuario.activo:
        raise Verificar2FaError("Código inválido.")

    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        raise Verificar2FaError(
            "Cuenta bloqueada por intentos 2FA fallidos. Contactá al administrador."
        )

    # Hash del código ingresado
    codigo_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

    # Verificar código (hash + expiración) via repo
    codigo_valido = await auth_repo.verificar_codigo_2fa(carnet, codigo_hash)
    if not codigo_valido:
        # Incrementar intentos y posible bloqueo
        nuevos_intentos = await auth_repo.incrementar_intentos_2fa(carnet)
        if nuevos_intentos >= 3:
            raise Verificar2FaError(
                "Cuenta bloqueada por 3 códigos inválidos. Contactá al administrador."
            )
        raise Verificar2FaError("Código inválido o expirado.")

    # Verificación exitosa: generar tokens
    await auth_repo.limpiar_codigo_2fa(carnet)
    usuario_id = cast(int, usuario.id)
    access_token = jwt_service.crear_access_token(usuario_id, str(usuario.rol))
    refresh_token = jwt_service.crear_refresh_token()

    # Guardar hash SHA-256 del refresh token
    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    expira_refresh = ahora + timedelta(days=7)
    await auth_repo.guardar_refresh_token(usuario_id, token_hash, expira_refresh)

    return Verificar2FaResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        rol=str(usuario.rol),
        carnet=usuario.carnet,
        nombre=usuario.nombre,
        id=usuario_id,
        cargo=usuario.cargo,
    )
