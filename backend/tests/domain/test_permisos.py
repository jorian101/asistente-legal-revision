"""Tests de la entidad de dominio de permisos y la matriz default por rol.

Decision `plan/permisos-crud-modulos`. Pure domain — sin DB, sin HTTP.
Cubre:
- PermisoCRUD.resolver: override anula default / None conserva default.
- PermisoEfectivo.permite: chequeo de operación.
- defaults_para_rol: matriz por rol, admin siempre full en TODAS las claves.
"""

from __future__ import annotations

from src.domain.entities.permiso import (
    TODAS_LAS_CLAVES,
    PermisoCRUD,
    PermisoEfectivo,
    defaults_para_rol,
)


def test_resolver_override_anula_default():
    default = PermisoCRUD(
        puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=True
    )
    override = PermisoCRUD(puede_crear=False)  # solo revoca crear

    resuelto = override.resolver(default)

    assert resuelto.puede_crear is False
    assert resuelto.puede_leer is True
    assert resuelto.puede_actualizar is True
    assert resuelto.puede_eliminar is True


def test_resolver_sin_override_conserva_default():
    default = PermisoCRUD(
        puede_crear=False, puede_leer=True, puede_actualizar=False, puede_eliminar=False
    )
    override = PermisoCRUD()  # todos None

    resuelto = override.resolver(default)

    assert resuelto == default


def test_resolver_override_otorga_permiso_que_default_deniega():
    default = PermisoCRUD(
        puede_crear=False, puede_leer=True, puede_actualizar=False, puede_eliminar=False
    )
    override = PermisoCRUD(puede_eliminar=True)

    resuelto = override.resolver(default)

    assert resuelto.puede_eliminar is True
    assert resuelto.puede_crear is False


def test_permiso_efectivo_permite():
    p = PermisoEfectivo(
        puede_crear=False, puede_leer=True, puede_actualizar=True, puede_eliminar=False
    )

    assert p.permite("leer") is True
    assert p.permite("actualizar") is True
    assert p.permite("crear") is False
    assert p.permite("eliminar") is False


def test_defaults_supervisor_tiene_expedientes_y_consultar():
    defaults = defaults_para_rol("supervisor")

    assert defaults["expedientes"].puede_crear is True
    assert defaults["consultar"].puede_leer is True
    # supervisor genera/edita borradores (auto de vista/dictamen) pero no elimina
    assert defaults["borradores"].puede_crear is True
    assert defaults["borradores"].puede_leer is True
    assert defaults["borradores"].puede_actualizar is True
    assert defaults["borradores"].puede_eliminar is False


def test_defaults_operador_tiene_borradores():
    defaults = defaults_para_rol("operador_juridico")

    assert "borradores" in defaults
    assert defaults["borradores"].puede_crear is True
    assert "sala_control" not in defaults  # admin-only


def test_admin_siempre_full_en_modulos_de_gestion():
    """El admin tiene full en TODOS los módulos de gestión del catálogo."""
    from src.domain.entities.permiso import MODULOS_CONSULTA

    defaults = defaults_para_rol("administrador")

    assert MODULOS_CONSULTA.isdisjoint(defaults.keys())  # sin consulta
    for modulo in defaults.values():
        assert modulo.puede_crear is True
        assert modulo.puede_leer is True
        assert modulo.puede_actualizar is True
        assert modulo.puede_eliminar is True
    # cubre todos los de gestión, incl. los nuevos (modulos, permisos)
    assert set(defaults.keys()) == TODAS_LAS_CLAVES - MODULOS_CONSULTA


def test_obras_es_modulo_consulta_admin_excluido():
    """'obras' es módulo de consulta: el admin NO accede (invariante de
    gestión); supervisor/operador mantienen acceso full vía DEFAULTS_POR_ROL."""
    admin = defaults_para_rol("administrador")
    supervisor = defaults_para_rol("supervisor")
    operador = defaults_para_rol("operador_juridico")

    assert "obras" not in admin
    assert supervisor["obras"].puede_crear is True
    assert supervisor["obras"].puede_eliminar is True
    assert operador["obras"].puede_crear is True
    assert operador["obras"].puede_eliminar is True


def test_rol_desconocido_no_tiene_modulos():
    assert defaults_para_rol("rol_inventado") == {}


def test_matriz_default_cubre_todas_las_claves_de_catalogos_conocidos():
    """Los roles supervisor/operador cubren los módulos de consulta conocidos."""
    from src.domain.entities.permiso import MODULOS_CONSULTA

    supervisor = defaults_para_rol("supervisor")
    operador = defaults_para_rol("operador_juridico")
    admin = defaults_para_rol("administrador")

    assert "expedientes" in supervisor
    assert "consultar" in supervisor
    assert "conversaciones" in supervisor
    assert "borradores" in supervisor  # genera/edita, no elimina
    assert supervisor["borradores"].puede_crear is True
    assert supervisor["borradores"].puede_leer is True
    assert supervisor["borradores"].puede_eliminar is False
    # 'chats' es un modulo embebido en /asistente/consultar (sin pagina propia):
    # supervisor y operador lo usan para sus chats privados (commit bfaffd0).
    assert "chats" in supervisor
    assert "expedientes" in operador
    assert "consultar" in operador
    assert "borradores" in operador
    assert operador["expedientes"].puede_crear is False  # no abre
    assert "chats" in operador
    assert set(admin.keys()) == TODAS_LAS_CLAVES - MODULOS_CONSULTA
