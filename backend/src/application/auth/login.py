"""Use case: Login de usuario (paso 1 del flujo 2FA).

Sprint 1 Auth (plan v3, HU-01) + Fase 2 plan jurado (2FA email obligatorio).
Recibe DI de AuthRepository + JwtService + EmailService.
Clean Architecture: no conoce HTTP, FastAPI ni SQLAlchemy.

Logica bloqueante Regla 2 Trail of Bits:
1. verificar usuario existe y esta activo
2. rate limit IP 5/min (contar_intentos_por_ip)
3. lockout carnet 10 fallidos/hora (contar_intentos_fallidos)
4. bcrypt verify password_hash
5. registrar intento (exitoso o fallido)

Flujo 2FA (Fase 2):
- Si el usuario tiene email_verificado=True -> genera codigo 6 digitos,
  guarda SHA-256 + expiracion 5 min, envia email y lanza Requiere2FaError
  (el router responde {requiere_2fa: true}; el frontend pide el codigo).
- Si NO tiene email_verificado -> login directo legacy (tokens inmediatos),
  manteniendo compatibilidad con usuarios seed sin 2FA configurado.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import bcrypt

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository
    from src.application.ports.email_service import EmailService
    from src.application.ports.jwt_service import JwtService

# Hash bcrypt (cost 12) de un secreto aleatorio descartado: nadie conoce su clave.
_HASH_SENUELO = "$2b$12$LLYiShCxY9kVthCtj6ZHju7JoDHdItfMxUS1fjV6tKTXFmLpY8z8q"


class LoginError(Exception):
    """Credenciales invalidas sin revelar motivo especifico."""


class RateLimitError(LoginError):
    """Demasiados intentos desde esta IP. Reintentar en 1 minuto."""


class LockoutError(LoginError):
    """Demasiados intentos fallidos para este carnet. Admin debe desbloquear."""


class Requiere2FaError(LoginError):
    """Credenciales validas, pero el usuario requiere codigo 2FA por email."""

    def __init__(self, carnet: str) -> None:
        self.carnet = carnet
        super().__init__("Se requiere verificacion 2FA por email.")


class ServicioEmailNoDisponibleError(LoginError):
    """No se pudo enviar el codigo 2FA por falla del servicio de email."""


@dataclass
class LoginResponse:
    access_token: str
    refresh_token: str
    rol: str
    carnet: str
    nombre: str
    id: int
    cargo: str


async def execute(
    carnet: str,
    password: str,
    ip: str,
    auth_repo: AuthRepository,
    jwt_service: JwtService,
    email_service: EmailService | None = None,
) -> LoginResponse:
    """Ejecuta el use case de login (paso 1: valida credenciales y dispara 2FA).

    Args:
        carnet: CI/CM alfanumerico.
        password: contrasena en texto plano (se verifica con bcrypt).
        ip: direccion IP del cliente para rate limit.
        auth_repo: implementacion de AuthRepository (inyectado).
        jwt_service: implementacion de JwtService (inyectado).
        email_service: EmailService (inyectado). Si es None, el login legacy
            emite tokens directos (sin 2FA).

    Returns:
        LoginResponse con access_token, refresh_token y rol (solo login legacy).

    Raises:
        RateLimitError: superado 5/min por IP.
        LockoutError: >= 10 fallidos en 1h por carnet.
        Requiere2FaError: credenciales validas + email_verificado -> pide codigo.
        LoginError: credenciales invalidas (sin UI de cual motivo).
    """
    ahora = datetime.now(UTC)

    intentos_ip = await auth_repo.contar_intentos_por_ip(ip, desde=ahora - timedelta(minutes=1))
    if intentos_ip >= 5:
        raise RateLimitError

    ventana_lockout = ahora - timedelta(hours=1)
    fallidos = await auth_repo.contar_intentos_fallidos(carnet, ventana_lockout)
    if fallidos >= 10:
        await auth_repo.registrar_intento(carnet, ip, exitoso=False)
        raise LockoutError

    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None or not usuario.activo:
        # Mismo costo que un login real: sin esto el tiempo de respuesta delata
        # que el carnet no existe o esta inactivo (enumeracion de usuarios).
        await asyncio.to_thread(
            bcrypt.checkpw, password.encode("utf-8"), _HASH_SENUELO.encode("utf-8")
        )
        await auth_repo.registrar_intento(carnet, ip, exitoso=False)
        raise LoginError

    # bcrypt es CPU-bound (~250 ms): fuera del event loop para no frenar a los demas requests.
    password_ok = await asyncio.to_thread(
        bcrypt.checkpw, password.encode("utf-8"), usuario.password_hash.encode("utf-8")
    )
    if not password_ok:
        await auth_repo.registrar_intento(carnet, ip, exitoso=False)
        raise LoginError

    # Login exitoso (credenciales correctas).
    await auth_repo.registrar_intento(carnet, ip, exitoso=True)

    # 2FA obligatorio: si el usuario tiene email verificado, pedir codigo.
    if usuario.email_verificado and usuario.email:
        if email_service is None:
            # Sin servicio email configurado, no podemos mandar el codigo.
            # Caemos a login legacy para no dejar al usuario afuera (dev mode).
            pass
        else:
            if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
                raise LockoutError
            codigo = f"{secrets.randbelow(10**6):06d}"
            codigo_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
            ttl_minutes = 5
            expira = ahora + timedelta(minutes=ttl_minutes)
            await auth_repo.guardar_codigo_2fa(carnet, codigo_hash, expira)
            try:
                await email_service.enviar_codigo_2fa(usuario.email, codigo, ttl_minutes)
            except Exception:
                with contextlib.suppress(Exception):
                    await auth_repo.limpiar_codigo_2fa(carnet)
                raise ServicioEmailNoDisponibleError from None
            raise Requiere2FaError(carnet)

    # Login legacy: tokens inmediatos (sin 2FA configurado).
    access_token = jwt_service.crear_access_token(cast(int, usuario.id), str(usuario.rol))
    refresh_token = jwt_service.crear_refresh_token()

    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    exp_refresh = ahora + timedelta(days=7)
    await auth_repo.guardar_refresh_token(cast(int, usuario.id), token_hash, exp_refresh)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        rol=str(usuario.rol),
        carnet=usuario.carnet,
        nombre=usuario.nombre,
        id=cast(int, usuario.id),
        cargo=usuario.cargo,
    )
