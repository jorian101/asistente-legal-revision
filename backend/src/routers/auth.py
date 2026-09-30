"""Router publico: login, refresh, logout, 2FA.

Sprint 1 Auth (plan v3, F1.5). Rate limit 5/min/IP en login, refresh
con cookie httpOnly, logout revoca refresh token.

Fase 2 plan jurado (2FA email):
- POST /auth/login: si usuario tiene email_verificado -> genera+envia codigo
  y responde {requiere_2fa: true, carnet}. Si no -> tokens directos (legacy).
- POST /auth/verificar-2fa: valida codigo 6 digitos -> emite JWT + refresh cookie.

Regla 2 Trail of Bits: cookie refresh httpOnly/Secure/SameSite=Strict.
El access token via en Authorization Bearer (memoria JS frontend).
"""

from __future__ import annotations

import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    EmailServiceDep,
    PermisoRepoDep,
    get_auth_repo,
    get_current_user,
    get_jwt_service,
)
from src.application.admin.audit import registrar_auditoria
from src.application.auth import actualizar_perfil, login, logout, refresh_token, verificar_2fa
from src.application.permisos import mis_permisos
from src.application.ports.auth_repository import AuthRepository
from src.application.ports.jwt_service import JwtService
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    carnet: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=6, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    rol: str
    carnet: str
    nombre: str
    id: int
    cargo: str


class Solicitar2FaResponse(BaseModel):
    requiere_2fa: bool
    carnet: str


class Verificar2FaRequest(BaseModel):
    carnet: str = Field(min_length=4, max_length=20)
    codigo: str = Field(min_length=6, max_length=6)


class Verificar2FaResponse(BaseModel):
    access_token: str
    rol: str
    carnet: str
    nombre: str
    id: int
    cargo: str


class PermisoModuloDTO(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    ruta: str
    orden: int
    puede_crear: bool
    puede_leer: bool
    puede_actualizar: bool
    puede_eliminar: bool


class PerfilDTO(BaseModel):
    id: int
    nombre: str
    carnet: str
    email: str | None
    rol: str
    cargo: str
    created_at: str | None


class ActualizarPerfilRequest(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    password_actual: str | None = Field(default=None, min_length=6, max_length=128)
    password_nueva: str | None = Field(default=None, min_length=6, max_length=128)


@router.post("/login", response_model=LoginResponse | Solicitar2FaResponse)
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    audit_repo: AuditLogRepoDep,
    email_service: EmailServiceDep,
):
    ip = request.client.host if request.client else "unknown"
    try:
        result = await login.execute(
            body.carnet, body.password, ip, auth_repo, jwt_service, email_service
        )
    except login.Requiere2FaError:
        # Credenciales validas + email verificado: codigo enviado, pedir 2FA.
        return Solicitar2FaResponse(requiere_2fa=True, carnet=body.carnet)
    except login.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Espera un minuto.",
        ) from None
    except login.LockoutError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cuenta bloqueada por reiterados intentos fallidos. Contacta al administrador.",
        ) from None
    except login.ServicioEmailNoDisponibleError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo enviar el código. Reintentá en unos segundos.",
        ) from None
    except login.LoginError:
        # R6: registrar intento fallido (append-only, no debe romper el login)
        with contextlib.suppress(Exception):
            await registrar_auditoria(
                audit_repo,
                accion="login_fallido",
                usuario_id=None,
                entidad="usuario",
                detalle={"carnet": body.carnet, "ip": ip},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        ) from None

    response.set_cookie(
        key="refresh_token",
        value=result.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    # R6: login exitoso (append-only, nunca debe romper el login)
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="login",
            usuario_id=result.id,
            entidad="usuario",
            entidad_id=result.id,
            detalle={"carnet": result.carnet, "ip": ip},
        )
    return LoginResponse(
        access_token=result.access_token,
        rol=result.rol,
        carnet=result.carnet,
        nombre=result.nombre,
        id=result.id,
        cargo=result.cargo,
    )


@router.post("/verificar-2fa", response_model=Verificar2FaResponse)
async def verificar_2fa_endpoint(
    body: Verificar2FaRequest,
    request: Request,
    response: Response,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
):
    ip = request.client.host if request.client else "unknown"
    try:
        result = await verificar_2fa.execute(body.carnet, body.codigo, ip, auth_repo, jwt_service)
    except verificar_2fa.Verificar2FaError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from None

    response.set_cookie(
        key="refresh_token",
        value=result.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    return Verificar2FaResponse(
        access_token=result.access_token,
        rol=result.rol,
        carnet=result.carnet,
        nombre=result.nombre,
        id=result.id,
        cargo=result.cargo,
    )


@router.post("/refresh")
async def refresh_endpoint(
    request: Request,
    response: Response,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
):
    cookie_value = request.cookies.get("refresh_token")
    if cookie_value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    try:
        result = await refresh_token.execute(cookie_value, auth_repo, jwt_service)
    except refresh_token.ReplayError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None
    except refresh_token.RefreshTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    response.set_cookie(
        key="refresh_token",
        value=result.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    return {"access_token": result.access_token}


@router.post("/logout", status_code=204)
async def logout_endpoint(
    request: Request,
    response: Response,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
):
    cookie_value = request.cookies.get("refresh_token")
    if cookie_value is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        await logout.execute(cookie_value, auth_repo)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from None

    # Se devuelve un Response propio: FastAPI no fusiona las cabeceras del inyectado.
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    respuesta.delete_cookie("refresh_token", httponly=True, secure=True, samesite="strict")
    return respuesta


@router.get("/permisos", response_model=list[PermisoModuloDTO])
async def permisos_usuario_endpoint(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    permiso_repo: PermisoRepoDep,
):
    """Permisos efectivos del usuario logueado sobre los módulos activos.

    Fase 2 del plan de módulos/permisos: el frontend usa esto para renderizar
    el sidebar dinámico (qué módulos ve y con qué operaciones). Re-valida
    contra BD en cada request (Regla 2 Trail of Bits).
    """
    modulos = await mis_permisos.execute(
        permiso_repo=permiso_repo,
        usuario_id=current_user.id,
        rol=current_user.rol,
    )
    return [
        PermisoModuloDTO(
            clave=m.clave,
            nombre=m.nombre,
            descripcion=m.descripcion,
            ruta=m.ruta,
            orden=m.orden,
            puede_crear=m.efectivo.puede_crear,
            puede_leer=m.efectivo.puede_leer,
            puede_actualizar=m.efectivo.puede_actualizar,
            puede_eliminar=m.efectivo.puede_eliminar,
        )
        for m in modulos
    ]


@router.get("/me", response_model=PerfilDTO)
async def obtener_perfil(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> PerfilDTO:
    """Devuelve el perfil del usuario autenticado sin exponer el hash."""
    return PerfilDTO(
        id=current_user.id,
        nombre=current_user.nombre,
        carnet=current_user.carnet,
        email=current_user.email,
        rol=current_user.rol,
        cargo=current_user.cargo,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


@router.patch("/me", response_model=PerfilDTO)
async def actualizar_perfil_propio(
    body: ActualizarPerfilRequest,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> PerfilDTO:
    """Actualiza nombre/email/contraseña; rol, cargo y carnet no son editables."""
    try:
        usuario = await actualizar_perfil.execute(
            auth_repo=auth_repo,
            usuario_id=current_user.id,
            nombre=body.nombre,
            email=body.email,
            password_actual=body.password_actual,
            password_nueva=body.password_nueva,
        )
    except actualizar_perfil.PerfilError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PerfilDTO(
        id=usuario.id,
        nombre=usuario.nombre,
        carnet=usuario.carnet,
        email=usuario.email,
        rol=usuario.rol,
        cargo=usuario.cargo,
        created_at=usuario.created_at.isoformat() if usuario.created_at else None,
    )
