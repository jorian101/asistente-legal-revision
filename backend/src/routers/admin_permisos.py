"""Router admin: gestión de módulos y permisos CRUD por usuario.

Decision `plan/permisos-crud-modulos`. Solo admin autenticado. Sección admin
para:
- GET /admin/modulos — catálogo fijo de módulos.
- PATCH /admin/modulos/{clave} — editar metadata (nombre/descripcion/ruta/orden/activo).
- GET /admin/usuarios/{carnet}/permisos — override + efectivo de un usuario.
- PUT /admin/usuarios/{carnet}/permisos — reemplazar overrides (nunca admin target).
- GET /admin/modulos-visibles — módulos efectivos por usuario y por rol.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    get_auth_repo,
    get_permiso_repo_dep,
    require_permiso,
)
from src.application.admin.audit import registrar_auditoria_segura
from src.application.permisos import (
    actualizar_modulo,
    asignar_permisos_usuario,
    listar_modulos,
    listar_permisos_usuario,
    modulos_visibles,
)
from src.application.ports.auth_repository import AuthRepository
from src.application.ports.permiso_repo import PermisoRepo
from src.domain.entities.permiso import Modulo, PermisoCRUD
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/admin", tags=["admin"])


class ModuloResponse(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    ruta: str
    orden: int
    activo: bool

    @classmethod
    def _from_entity(cls, m: Modulo) -> ModuloResponse:
        return cls(
            clave=m.clave,
            nombre=m.nombre,
            descripcion=m.descripcion,
            ruta=m.ruta,
            orden=m.orden,
            activo=m.activo,
        )


class ActualizarModuloRequest(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=255)
    ruta: str | None = Field(None, min_length=1, max_length=255)
    orden: int | None = Field(None, ge=0, le=100)
    activo: bool | None = None


class PermisoCRUDRequest(BaseModel):
    puede_crear: bool | None = None
    puede_leer: bool | None = None
    puede_actualizar: bool | None = None
    puede_eliminar: bool | None = None


class PermisoModuloResponse(BaseModel):
    clave: str
    nombre: str
    override: PermisoCRUDRequest
    efectivo: PermisoCRUDRequest
    default_rol: PermisoCRUDRequest


class AsignarPermisosRequest(BaseModel):
    permisos: dict[str, PermisoCRUDRequest]


class ModuloVisibleResponse(BaseModel):
    clave: str
    nombre: str
    descripcion: str
    ruta: str


class ModulosVisiblesResponse(BaseModel):
    por_usuario: dict[str, list[ModuloVisibleResponse]]
    por_rol: dict[str, list[ModuloVisibleResponse]]


@router.get("/modulos-visibles", response_model=ModulosVisiblesResponse)
async def modulos_visibles_endpoint(
    _admin: Annotated[Usuario, Depends(require_permiso("usuarios", "leer"))],
    permiso_repo: Annotated[PermisoRepo, Depends(get_permiso_repo_dep)],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
):
    """Módulos efectivos (activos + leer) de cada usuario y de cada rol."""
    dto = await modulos_visibles.execute(permiso_repo, auth_repo)
    return ModulosVisiblesResponse(
        por_usuario={
            carnet: [ModuloVisibleResponse(**vars(m)) for m in mods]
            for carnet, mods in dto.por_usuario.items()
        },
        por_rol={
            rol: [ModuloVisibleResponse(**vars(m)) for m in mods]
            for rol, mods in dto.por_rol.items()
        },
    )


@router.get("/modulos", response_model=list[ModuloResponse])
async def listar_modulos_endpoint(
    _admin: Annotated[Usuario, Depends(require_permiso("modulos", "leer"))],
    permiso_repo: Annotated[PermisoRepo, Depends(get_permiso_repo_dep)],
):
    """Lista el catálogo fijo de módulos del sistema."""
    modulos = await listar_modulos.execute(permiso_repo)
    return [ModuloResponse._from_entity(m) for m in modulos]


@router.patch("/modulos/{clave}", response_model=ModuloResponse)
async def actualizar_modulo_endpoint(
    clave: str,
    body: ActualizarModuloRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("modulos", "actualizar"))],
    permiso_repo: Annotated[PermisoRepo, Depends(get_permiso_repo_dep)],
    audit_repo: AuditLogRepoDep,
):
    """Edita metadata de un módulo del catálogo (nombre/descripcion/ruta/orden/activo)."""
    campos = body.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe enviar al menos un campo a modificar.",
        )
    try:
        modulo = await actualizar_modulo.execute(permiso_repo, clave=clave, **campos)
    except actualizar_modulo.ModuloNoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    await registrar_auditoria_segura(
        audit_repo,
        accion="actualizar_modulo",
        usuario_id=_admin.id,
        entidad="modulo",
        detalle={"clave": clave, "campos": campos},
    )
    return ModuloResponse._from_entity(modulo)


@router.get("/usuarios/{carnet}/permisos", response_model=list[PermisoModuloResponse])
async def listar_permisos_usuario_endpoint(
    carnet: str,
    _admin: Annotated[Usuario, Depends(require_permiso("permisos", "leer"))],
    permiso_repo: Annotated[PermisoRepo, Depends(get_permiso_repo_dep)],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
):
    """Lista permisos (override + efectivo) de un usuario sobre todos los módulos."""
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    detalle = await listar_permisos_usuario.execute(
        permiso_repo=permiso_repo,
        auth_repo=auth_repo,
        usuario_id=usuario.id or 0,
        rol=usuario.rol,
    )
    return [
        PermisoModuloResponse(
            clave=d.clave,
            nombre=d.nombre,
            override=PermisoCRUDRequest(
                puede_crear=d.override.puede_crear,
                puede_leer=d.override.puede_leer,
                puede_actualizar=d.override.puede_actualizar,
                puede_eliminar=d.override.puede_eliminar,
            ),
            efectivo=PermisoCRUDRequest(
                puede_crear=d.efectivo.puede_crear,
                puede_leer=d.efectivo.puede_leer,
                puede_actualizar=d.efectivo.puede_actualizar,
                puede_eliminar=d.efectivo.puede_eliminar,
            ),
            default_rol=PermisoCRUDRequest(
                puede_crear=d.default_rol.puede_crear,
                puede_leer=d.default_rol.puede_leer,
                puede_actualizar=d.default_rol.puede_actualizar,
                puede_eliminar=d.default_rol.puede_eliminar,
            ),
        )
        for d in detalle
    ]


@router.put("/usuarios/{carnet}/permisos", status_code=status.HTTP_204_NO_CONTENT)
async def asignar_permisos_usuario_endpoint(
    carnet: str,
    body: AsignarPermisosRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("permisos", "actualizar"))],
    permiso_repo: Annotated[PermisoRepo, Depends(get_permiso_repo_dep)],
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
):
    """Reemplaza los overrides de permisos de un usuario (no admin target)."""
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    permisos = {
        clave: PermisoCRUD(
            puede_crear=p.puede_crear,
            puede_leer=p.puede_leer,
            puede_actualizar=p.puede_actualizar,
            puede_eliminar=p.puede_eliminar,
        )
        for clave, p in body.permisos.items()
    }
    try:
        await asignar_permisos_usuario.execute(
            permiso_repo=permiso_repo,
            auth_repo=auth_repo,
            usuario_id=usuario.id or 0,
            permisos=permisos,
        )
    except asignar_permisos_usuario.UsuarioAdministradorNoModificableError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden modificar los permisos de un administrador.",
        ) from None
    except asignar_permisos_usuario.ModuloNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una clave de módulo no existe en el catálogo.",
        ) from None
    await registrar_auditoria_segura(
        audit_repo,
        accion="asignar_permisos",
        usuario_id=_admin.id,
        entidad="usuario",
        entidad_id=usuario.id,
        detalle={"carnet": carnet, "modulos": sorted(body.permisos)},
    )
    return None
