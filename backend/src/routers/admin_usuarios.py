"""Router admin: gestion de usuarios (HU-01, HU-02).

Sprint 1 Auth (plan v3, F1.5). Solo admin autenticado.

HU-01: Crear usuario (POST /admin/usuarios).
HU-02: Modificar usuario (PATCH) + Reset password (POST /reset-password).
"""

from __future__ import annotations

import contextlib
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    get_auth_repo,
    require_permiso,
)
from src.application.admin.audit import registrar_auditoria
from src.application.auth import (
    crear_usuario,
    desbloquear_2fa,
    listar_usuarios,
    modificar_usuario,
    reset_password,
)
from src.application.ports.auth_repository import AuthRepository
from src.domain.entities.usuario import CargoInvalidoParaRolError, Usuario

router = APIRouter(prefix="/admin", tags=["admin"])


class CrearUsuarioRequest(BaseModel):
    carnet: str = Field(min_length=4, max_length=20)
    nombre: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    rol: Literal["administrador", "supervisor", "operador_juridico"]
    cargo: str = Field(min_length=2, max_length=50)
    email: str | None = Field(None, max_length=255)


class UsuarioResponse(BaseModel):
    id: int
    carnet: str
    nombre: str
    rol: str
    cargo: str
    activo: bool
    email: str | None = None
    email_verificado: bool = False

    @classmethod
    def _from_entity(cls, usuario: Usuario) -> UsuarioResponse:
        return cls(
            id=cast(int, usuario.id),
            carnet=usuario.carnet,
            nombre=usuario.nombre,
            rol=usuario.rol,
            cargo=usuario.cargo,
            activo=usuario.activo,
            email=usuario.email,
            email_verificado=usuario.email_verificado,
        )


class ModificarUsuarioRequest(BaseModel):
    rol: Literal["administrador", "supervisor", "operador_juridico"] | None = None
    cargo: str | None = Field(None, min_length=2, max_length=50)
    activo: bool | None = None
    email: str | None = Field(None, max_length=255)
    nombre: str | None = Field(None, min_length=2, max_length=100)
    carnet_nuevo: str | None = Field(None, min_length=4, max_length=20)


class ResetPasswordRequest(BaseModel):
    nueva_password: str = Field(min_length=6, max_length=128)


@router.get("/usuarios", response_model=list[UsuarioResponse])
async def listar_usuarios_endpoint(
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "leer"))],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
):
    """HU-02: lista todos los usuarios (solo admin)."""
    usuarios = await listar_usuarios.execute(auth_repo)
    return [UsuarioResponse._from_entity(u) for u in usuarios]


@router.post("/usuarios", response_model=UsuarioResponse)
async def crear_usuario_endpoint(
    body: CrearUsuarioRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "crear"))],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
):
    try:
        usuario = await crear_usuario.execute(
            carnet=body.carnet,
            nombre=body.nombre,
            password=body.password,
            rol=body.rol,
            cargo=body.cargo,
            email=body.email,
            auth_repo=auth_repo,
        )
    except crear_usuario.CarnetDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El carnet ya esta registrado.",
        ) from None
    except CargoInvalidoParaRolError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="crear_usuario",
            usuario_id=_admin.id,
            entidad="usuario",
            entidad_id=usuario.id,
            detalle={"carnet": usuario.carnet, "rol": usuario.rol},
        )

    return UsuarioResponse._from_entity(usuario)


@router.patch("/usuarios/{carnet}", response_model=UsuarioResponse)
async def modificar_usuario_endpoint(
    carnet: str,
    body: ModificarUsuarioRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "actualizar"))],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
):
    try:
        usuario = await modificar_usuario.execute(
            carnet,
            auth_repo,
            rol=body.rol,
            cargo=body.cargo,
            activo=body.activo,
            email=body.email,
            nombre=body.nombre,
            carnet_nuevo=body.carnet_nuevo,
        )
    except modificar_usuario.UsuarioNoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    except CargoInvalidoParaRolError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    except crear_usuario.CarnetDuplicadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El carnet ya esta registrado.",
        ) from None

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="modificar_usuario",
            usuario_id=_admin.id,
            entidad="usuario",
            entidad_id=usuario.id,
            detalle=body.model_dump(exclude_none=True),
        )

    return UsuarioResponse._from_entity(usuario)


@router.post("/usuarios/{carnet}/desbloquear-2fa")
async def desbloquear_2fa_endpoint(
    carnet: str,
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "actualizar"))],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
):
    """Desbloquea 2FA de un usuario bloqueado por 3 codigos invalidos."""
    try:
        await desbloquear_2fa.execute(carnet, auth_repo)
    except desbloquear_2fa.UsuarioNoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None

    # Trail of Bits R6: levantar un bloqueo de 2FA es accion sensitiva.
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="desbloquear_2fa",
            usuario_id=_admin.id,
            entidad="usuario",
            detalle={"carnet": carnet},
        )

    return {"message": "2FA desbloqueado correctamente."}


@router.post("/usuarios/{carnet}/reset-password")
async def reset_password_endpoint(
    carnet: str,
    body: ResetPasswordRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "actualizar"))],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
):
    try:
        await reset_password.execute(carnet, body.nueva_password, auth_repo)
    except reset_password.UsuarioNoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None

    # Trail of Bits R6: se registra la accion, nunca la password.
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="reset_password",
            usuario_id=_admin.id,
            entidad="usuario",
            detalle={"carnet": carnet},
        )

    return {"message": "Password actualizada correctamente."}
