"""Entidades de dominio del sistema de permisos CRUD por modulo.

Regla Clean Architecture: estas entidades NO dependen de SQLAlchemy ni de
Pydantic. Son dataclasses puras que encapsulan las reglas de negocio de los
permisos de acceso. El ORM vive en adapters/postgres/models/ y mapea estas
entidades a las tablas `modulo` y `usuario_modulo_permiso`.

Decision de diseno (ver Engram `plan/permisos-crud-modulos`):
- Los roles (administrador/supervisor/operador_juridico) definen la matriz
  DEFAULT de acceso por modulo.
- El admin puede anular/ajustar permisos CRUD por USUARIO individual
  (overrides en `usuario_modulo_permiso`). Un override con valor None
  significa "seguir el default del rol" (el override parcial es explicito).
- El rol administrador SIEMPRE tiene acceso full (regla inamovible de
  seguridad: nunca se puede quitar acceso al admin).
"""

from __future__ import annotations

from dataclasses import dataclass, field

RolUsuario = str
ClaveModulo = str


@dataclass(frozen=True)
class PermisoCRUD:
    """Flags de operaciones CRUD sobre un modulo.

    None = sin override (seguir el default del rol). True/False = override
    explicito que anula el default.
    """

    puede_crear: bool | None = None
    puede_leer: bool | None = None
    puede_actualizar: bool | None = None
    puede_eliminar: bool | None = None

    def resolver(self, default: PermisoCRUD) -> PermisoCRUD:
        """Combina el default del rol con este override.

        Regla: cada flag explicito (True/False) del override anula el default;
        cada flag None conserva el default del rol.
        """
        return PermisoCRUD(
            puede_crear=default.puede_crear if self.puede_crear is None else self.puede_crear,
            puede_leer=default.puede_leer if self.puede_leer is None else self.puede_leer,
            puede_actualizar=(
                default.puede_actualizar if self.puede_actualizar is None else self.puede_actualizar
            ),
            puede_eliminar=(
                default.puede_eliminar if self.puede_eliminar is None else self.puede_eliminar
            ),
        )


@dataclass(frozen=True)
class PermisoEfectivo:
    """Permiso CRUD ya resuelto (defaults de rol ⊕ overrides de usuario)."""

    puede_crear: bool
    puede_leer: bool
    puede_actualizar: bool
    puede_eliminar: bool

    def permite(self, operacion: str) -> bool:
        """True si la operacion CRUD esta permitida."""
        return getattr(self, _OPERACION_TO_ATTR[operacion])


_OPERACION_TO_ATTR = {
    "crear": "puede_crear",
    "leer": "puede_leer",
    "actualizar": "puede_actualizar",
    "eliminar": "puede_eliminar",
}


@dataclass(frozen=True)
class Modulo:
    """Modulo del sistema (catálogo fijo, sembrado por migracion).

    Atributos:
        clave: slug unico del modulo (ej. 'usuarios', 'corpus', 'consultar').
            Es el identificador usado por los guards require_permiso.
        nombre: nombre legible para la UI.
        descripcion: descripcion corta para tooltips/sidebar.
        ruta: ruta frontend del modulo.
        orden: posicion en el sidebar.
        activo: si el modulo esta habilitado en el sistema.
    """

    clave: str
    nombre: str
    descripcion: str
    ruta: str
    orden: int = 0
    activo: bool = True
    id: int | None = None


@dataclass(frozen=True)
class PermisoUsuarioModulo:
    """Override de permisos de un usuario sobre un modulo (tabla puente).

    PermisoCRUD con todos los flags en None = "sin override, seguir rol".
    """

    usuario_id: int
    modulo_clave: str
    permisos: PermisoCRUD = field(default_factory=PermisoCRUD)


# ---------------------------------------------------------------------------
# Matriz DEFAULT por rol (código, no BD — decisión del plan).
# Espeja MODULOS_MATRIZ del frontend (frontend/src/config/modulosPorRol.ts) y
# los guards del backend (require_admin/supervisor/operador/consulta_user).
# ---------------------------------------------------------------------------

#: Flags CRUD por defecto cuando un rol tiene acceso a un modulo.
_FULL = PermisoCRUD(puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=True)

#: Módulos de CONSULTA (bounded context asistente). El rol administrador NO
#: tiene acceso a ellos (es de gestión): espeja require_consulta_user que
#: bloquea al admin del flujo de consulta. `defaults_para_rol` los excluye.
MODULOS_CONSULTA = frozenset(
    {"consultar", "conversaciones", "expedientes", "obras", "borradores", "chats"}
)

#: Operador: trabaja dentro de expedientes abiertos por el supervisor — carga,
#: publica y elimina obras (Regla 5) pero NO abre ni edita ni archiva expedientes.
_OPERADOR_EXPEDIENTES = PermisoCRUD(
    puede_crear=False, puede_leer=True, puede_actualizar=False, puede_eliminar=False
)

#: Obras (obrados del expediente): carga, publicación y eliminación con reglas
#: finas por propietario en el dominio (Regla 5). Módulo separado de
#: 'expedientes' para que editar el expediente quede solo-supervisor sin
#: bloquear las operaciones de archivos (bug fix tras commit 0af2a54).
_OBRAS_OPERADOR = _FULL

#: Operador: puede PROponer doctrina (privado->publicado) y SELECCIONAR
#: doctrina global (copiar a su expediente/consulta). No puede aprobar/rechazar
#: (eso es del supervisor).
_OPERADOR_DOCTRINA = PermisoCRUD(
    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=False
)

#: Supervisor: aprueba/rechaza doctrina global, carga directa (auto-aprueba).
#: Ve pendientes + aprobadas.
_SUPERVISOR_DOCTRINA = PermisoCRUD(
    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=True
)

#: Supervisor: genera y gestiona sus obrados (auto de vista/dictamen) pero no
#: elimina. Aprueba oficial, desoficializa (actualizar) y edita contenido.
_SUPERVISOR_BORRADORES = PermisoCRUD(
    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=False
)

#: Chats privados: supervisor y operador crean/leen/gestionan sus propios chats
#: (capacidad embebida en /asistente/consultar, sin página propia). Sin endpoint
#: de eliminar; archivar se resuelve como actualizar.
_CHATS_USUARIO = _FULL

#: Formatos TSJM: supervisor ve y corrige bloques/layouts, promueve canónicos.
#: No elimina (curaduría segura). Admin tiene _FULL vía defaults_para_rol.
_FORMATOS_SUPERVISOR = PermisoCRUD(
    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=False
)

#: Matriz completa de acceso por rol -> modulo -> permisos default.
#: Espeja los guards que migramos a require_permiso (require_admin,
#: require_consulta_user, require_supervisor, require_operador).
DEFAULTS_POR_ROL: dict[RolUsuario, dict[ClaveModulo, PermisoCRUD]] = {
    "administrador": {
        "usuarios": _FULL,
        "corpus": _FULL,
        "metricas": _FULL,
        "sala_control": _FULL,
        "auditoria": _FULL,  # append-only: sin endpoints de escritura
        "consultas_rag": _FULL,  # append-only: sin endpoints de escritura
        "modulos": _FULL,
        "permisos": _FULL,
    },
    "supervisor": {
        "expedientes": _FULL,  # abre y gestiona expedientes
        "obras": _FULL,  # carga, publica y elimina obrados
        "doctrina": _SUPERVISOR_DOCTRINA,  # aprueba/rechaza/carga global
        "consultar": _FULL,
        "conversaciones": _FULL,
        "borradores": _SUPERVISOR_BORRADORES,  # genera/edita, no elimina
        "chats": _CHATS_USUARIO,  # chats privados del asistente (embebido)
        "formatos": _FORMATOS_SUPERVISOR,  # ve/corrige layouts y promueve canónicos
    },
    "operador_juridico": {
        "expedientes": _OPERADOR_EXPEDIENTES,  # no abre, trabaja en obras
        "obras": _OBRAS_OPERADOR,  # carga/publica/elimina sus obrados (Regla 5)
        "doctrina": _OPERADOR_DOCTRINA,  # propone y selecciona global
        "consultar": _FULL,
        "conversaciones": _FULL,
        "borradores": _FULL,
        "chats": _CHATS_USUARIO,  # chats privados del asistente (embebido)
    },
}

#: Claves de todos los modulos del catálogo fijo (seed de la migracion).
TODAS_LAS_CLAVES = frozenset(
    [
        "usuarios",
        "corpus",
        "metricas",
        "sala_control",
        "auditoria",
        "consultas_rag",
        "modulos",
        "permisos",
        "expedientes",
        "obras",
        "consultar",
        "conversaciones",
        "borradores",
        "chats",
        "doctrina",
        "criterios",
        "formatos",
    ]
)


def defaults_para_rol(rol: str) -> dict[ClaveModulo, PermisoCRUD]:
    """Devuelve la matriz default del rol.

    Regla de seguridad del admin: full sobre TODOS los módulos de gestión del
    catálogo (aunque un módulo nuevo no esté en la matriz explícita). Los
    módulos de consulta se excluyen SIEMPRE del admin (es de gestión, espeja
    require_consulta_user).
    """
    if rol == "administrador":
        base = dict(DEFAULTS_POR_ROL["administrador"])
        for clave in TODAS_LAS_CLAVES - MODULOS_CONSULTA:
            base.setdefault(clave, _FULL)
        return base
    return dict(DEFAULTS_POR_ROL.get(rol, {}))
