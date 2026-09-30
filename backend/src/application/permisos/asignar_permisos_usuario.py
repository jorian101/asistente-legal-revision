"""Use case: Asignar (reemplazar) overrides de permisos CRUD de un usuario.

El admin edita la matriz de permisos de un usuario. `permisos` es un dict
{clave_modulo: PermisoCRUD} donde cada flag puede ser:
- None: sin override → seguir el default del rol.
- True/False: override explícito que anula el default.

Regla de seguridad inamovible (decision `plan/permisos-crud-modulos`):
NUNCA se permite modificar permisos de un administrador — el rol admin
siempre tiene acceso full y su override no puede degradarlo.
"""

from __future__ import annotations

from src.domain.entities.permiso import PermisoCRUD


class UsuarioNoEncontradoError(Exception):
    """El usuario no existe."""


class UsuarioAdministradorNoModificableError(Exception):
    """No se pueden modificar los permisos de un administrador (regla de seguridad)."""


class ModuloNoEncontradoError(Exception):
    """Una clave de módulo del dict no existe en el catálogo."""


async def execute(
    permiso_repo,
    auth_repo,
    usuario_id: int,
    permisos: dict[str, PermisoCRUD],
) -> None:
    """Reemplaza los overrides de permisos del usuario.

    Raises:
        UsuarioNoEncontradoError: si el usuario no existe.
        UsuarioAdministradorNoModificableError: si el target es administrador.
        ModuloNoEncontradoError: si una clave de módulo no existe.
    """
    target = await auth_repo.get_by_id(usuario_id)
    if target is None:
        raise UsuarioNoEncontradoError(usuario_id)
    if target.rol == "administrador":
        raise UsuarioAdministradorNoModificableError(usuario_id)

    try:
        await permiso_repo.reemplazar_permisos_usuario(usuario_id, permisos)
    except KeyError as exc:
        raise ModuloNoEncontradoError(str(exc)) from None
