"""Entidad de dominio Usuario.

Regla Clean Architecture: esta entidad NO depende de SQLAlchemy ni de Pydantic.
Es una dataclass pura que encapsula las reglas de negocio del usuario. El ORM
(SQLAlchemy) vive en adapters/postgres/models/ y mapea esta entidad a la tabla
`usuario`. Pydantic se reserva para los DTOs/schemas de la capa de routers.

Diferenciacion clave (decision de arquitectura, ver Engram topic
`arquitectura/entidad-usuario`):
- `rol`: permiso del sistema (administrador / supervisor / operador_juridico).
  Define autorizacion en la aplicacion.
- `cargo`: rol institucional real (Auditor, Fiscal, Vocal Relator, etc.).
  Necesario para inyectar el contexto correcto en los prompts del LLM en el RAG.

Sprint 1 (plan v3, decision D1): el identificador de inicio de sesion es el
Carnet de Identidad (CI) o Carnet Militar (CM), string alfanumerico. Antes era
`usuario` (username generico), renombrado a `carnet` via migracion Alembic M1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RolUsuario = Literal["administrador", "supervisor", "operador_juridico"]

#: Cargos institucionales (marco-practico Tabla 12). El administrador es
#: personal tecnico/TI, NO pertenece a la SAC.
CargoUsuario = Literal[
    "Auditor",
    "Fiscal",
    "Vocal Relator",
    "Secretaria de Cámara",
    "Vocal Presidente",
    "Auxiliar de Secretaría de Cámara",
    "Personal Técnico",
]

#: Cargos validos por rol (Tabla 12: Operador = Auditor/Fiscal/Vocal Relator/
#: Secretaria de Camara; Supervisor = Vocal Presidente/Auxiliar; Admin =
#: personal tecnico). Sin "Otro": los cargos fuera de la SAC se agregaran
#: cuando esos perfiles accedan al asistente.
CARGOS_POR_ROL: dict[RolUsuario, frozenset[CargoUsuario]] = {
    "administrador": frozenset({"Personal Técnico"}),
    "operador_juridico": frozenset({"Auditor", "Fiscal", "Vocal Relator", "Secretaria de Cámara"}),
    "supervisor": frozenset({"Vocal Presidente", "Auxiliar de Secretaría de Cámara"}),
}


class CargoInvalidoParaRolError(ValueError):
    """El cargo no corresponde al rol (Tabla 12)."""


def cargos_validos_para_rol(rol: str) -> frozenset[str]:
    """Cargos permitidos para un rol (Tabla 12). Rol desconocido -> vacio."""
    return CARGOS_POR_ROL.get(rol, frozenset())


def validar_cargo_para_rol(rol: str, cargo: str) -> None:
    """Valida que el cargo corresponda al rol.

    Raises:
        CargoInvalidoParaRolError: si el cargo no es valido para el rol.
    """
    if cargo not in cargos_validos_para_rol(rol):
        permitidos = ", ".join(sorted(cargos_validos_para_rol(rol))) or "ninguno"
        raise CargoInvalidoParaRolError(
            f"El cargo '{cargo}' no corresponde al rol '{rol}'. "
            f"Cargos validos para '{rol}': {permitidos}."
        )


@dataclass
class Usuario:
    """Usuario del sistema asistente-legal.

    Atributos:
        id: Identificador interno. None si la entidad no fue persistida aun.
        nombre: Nombre completo del usuario.
        carnet: Carnet de Identidad (CI) o Carnet Militar (CM), alfanumerico.
            Identificador de inicio de sesion unico en la tabla.
        password_hash: Hash bcrypt de la contrasenia. Nunca en texto plano.
        rol: Perfil de acceso del sistema. Ver RolUsuario.
        cargo: Rol institucional real (Auditor, Fiscal, Vocal Relator, etc.).
            Se usa para personalizar el contexto inyectado al LLM en el RAG.
        activo: True si el usuario puede iniciar sesion. False = baja logica.
        created_at: Fecha/hora de alta. None antes de persistir.
        email: Email asociado para el segundo factor.
        email_verificado: Indica si el email fue verificado.
        codigo_2fa_hash: Hash del código temporal vigente.
        codigo_2fa_expira: Expiración del código temporal.
        intentos_codigo: Intentos inválidos acumulados.
        bloqueado_hasta: Fin del bloqueo por intentos 2FA inválidos.
    """

    id: int | None
    nombre: str
    carnet: str
    password_hash: str
    rol: RolUsuario
    cargo: str
    activo: bool = True
    created_at: datetime | None = None
    email: str | None = None
    email_verificado: bool = False
    codigo_2fa_hash: str | None = None
    codigo_2fa_expira: datetime | None = None
    intentos_codigo: int = 0
    bloqueado_hasta: datetime | None = None
