"""Tests de use cases de permisos CRUD por módulo.

Decision `plan/permisos-crud-modulos`. Use cases puros — no DB, no HTTP.
Fakes que cumplen los Protocol PermisoRepo y AuthRepository.

Cubre:
- resolver_permisos_usuario: defaults del rol, override anula default,
  override otorga permiso, admin siempre full, rol sin módulo → denegado.
- asignar_permisos_usuario: reemplaza overrides, target admin bloqueado,
  usuario inexistente, módulo desconocido.
- listar_permisos_usuario: efectivo refleja override; usuario inexistente.
"""

from __future__ import annotations

from dataclasses import replace
from typing import override

import pytest

from src.application.permisos import (
    asignar_permisos_usuario,
    listar_permisos_usuario,
    mis_permisos,
    modulos_visibles,
    resolver_permisos_usuario,
)
from src.domain.entities.permiso import Modulo, PermisoCRUD
from src.domain.entities.usuario import Usuario
from tests._factories import make_admin, make_usuario


class FakePermisoRepo:
    """PermisoRepo in-memory. `overrides` es {usuario_id: {clave: PermisoCRUD}}."""

    def __init__(
        self,
        modulos: list[Modulo] | None = None,
        overrides: dict[int, dict[str, PermisoCRUD]] | None = None,
    ) -> None:
        self.modulos = modulos or [
            Modulo(
                clave="consultar",
                nombre="Consultar",
                descripcion="",
                ruta="/asistente/consultar",
                orden=8,
            ),
            Modulo(
                clave="expedientes",
                nombre="Expedientes",
                descripcion="",
                ruta="/asistente/expedientes",
                orden=7,
            ),
            Modulo(
                clave="borradores",
                nombre="Borradores",
                descripcion="",
                ruta="/asistente/borradores",
                orden=10,
            ),
            Modulo(
                clave="corpus",
                nombre="Corpus Jurídico",
                descripcion="",
                ruta="/admin/corpus",
                orden=2,
            ),
            Modulo(
                clave="chats",
                nombre="Chats privados",
                descripcion="",
                ruta="/asistente/chats",
                orden=13,
            ),
        ]
        self.overrides = dict(overrides or {})
        self.reemplazos: list[tuple[int, dict[str, PermisoCRUD]]] = []

    @override
    async def listar_modulos(self) -> list[Modulo]:
        return self.modulos

    @override
    async def actualizar_modulo(self, clave: str, **campos) -> Modulo:
        for modulo in self.modulos:
            if modulo.clave == clave:
                for k, v in campos.items():
                    setattr(modulo, k, v)
                return modulo
        raise KeyError(clave)

    @override
    async def get_permisos_usuario(self, usuario_id: int) -> dict[str, PermisoCRUD]:
        return dict(self.overrides.get(usuario_id, {}))

    @override
    async def reemplazar_permisos_usuario(
        self, usuario_id: int, permisos: dict[str, PermisoCRUD]
    ) -> None:
        claves_validas = {m.clave for m in self.modulos}
        desconocidas = set(permisos.keys()) - claves_validas
        if desconocidas:
            raise KeyError(", ".join(sorted(desconocidas)))
        self.overrides[usuario_id] = dict(permisos)
        self.reemplazos.append((usuario_id, dict(permisos)))


class FakeAuthRepo:
    """AuthRepository in-memory minimo para los UCs de permisos."""

    def __init__(self, usuarios: list[Usuario]) -> None:
        self._por_id: dict[int, Usuario] = {u.id: u for u in usuarios if u.id is not None}
        self._por_carnet: dict[str, Usuario] = {u.carnet: u for u in usuarios}

    @override
    async def get_by_id(self, usuario_id: int) -> Usuario | None:
        return self._por_id.get(usuario_id)

    @override
    async def get_by_carnet(self, carnet: str) -> Usuario | None:
        return self._por_carnet.get(carnet)

    @override
    async def listar_usuarios(self) -> list[Usuario]:
        return list(self._por_id.values())


def _usuario(**kwargs) -> Usuario:
    return make_usuario(**kwargs)


# --- resolver_permisos_usuario ---


async def test_resolver_usa_default_del_rol_sin_overrides():
    repo = FakePermisoRepo()
    operador = _usuario(id=1, rol="operador_juridico")

    efectivos = await resolver_permisos_usuario.execute(repo, operador.id or 0, operador.rol)

    assert efectivos["consultar"].puede_leer is True
    assert efectivos["borradores"].puede_crear is True
    # operador no tiene corpus (admin-only) → módulo presente pero sin permiso
    assert efectivos["corpus"].puede_leer is False
    # chats es capacidad del asistente: operador gestiona sus propios chats
    assert efectivos["chats"].puede_crear is True
    assert efectivos["chats"].puede_leer is True


async def test_resolver_override_revoca_permiso_del_default():
    repo = FakePermisoRepo(overrides={1: {"consultar": PermisoCRUD(puede_leer=False)}})
    operador = _usuario(id=1, rol="operador_juridico")

    efectivos = await resolver_permisos_usuario.execute(repo, operador.id or 0, operador.rol)

    assert efectivos["consultar"].puede_leer is False
    assert efectivos["borradores"].puede_crear is True  # default intacto


async def test_resolver_override_otorga_modulo_admin_only():
    repo = FakePermisoRepo(overrides={1: {"corpus": PermisoCRUD(puede_leer=True)}})
    operador = _usuario(id=1, rol="operador_juridico")

    efectivos = await resolver_permisos_usuario.execute(repo, operador.id or 0, operador.rol)

    assert efectivos["corpus"].puede_leer is True
    assert efectivos["corpus"].puede_crear is False  # override parcial


async def test_resolver_admin_siempre_full_en_gestion_sin_consulta():
    repo = FakePermisoRepo(overrides={1: {"corpus": PermisoCRUD(puede_leer=False)}})
    admin = make_admin(id=1)

    efectivos = await resolver_permisos_usuario.execute(repo, admin.id or 0, admin.rol)

    # corpus es gestión → full (el override del admin nunca degrada)
    for op in ("puede_crear", "puede_leer", "puede_actualizar", "puede_eliminar"):
        assert getattr(efectivos["corpus"], op) is True
    # consultar/expedientes/borradores son consulta → denegados
    assert efectivos["consultar"].puede_leer is False
    assert efectivos["expedientes"].puede_crear is False
    assert efectivos["borradores"].puede_crear is False


async def test_resolver_modulo_inactivo_deniega_salvo_admin():
    repo = FakePermisoRepo()
    repo.modulos = [
        replace(m, activo=False) if m.clave in ("consultar", "corpus") else m for m in repo.modulos
    ]
    operador = _usuario(id=1, rol="operador_juridico")
    admin = make_admin(id=2)

    efectivos_op = await resolver_permisos_usuario.execute(repo, 1, operador.rol)
    efectivos_admin = await resolver_permisos_usuario.execute(repo, 2, admin.rol)

    # Desactivado: el operador pierde todo, aunque su rol lo tenía.
    for op in ("puede_crear", "puede_leer", "puede_actualizar", "puede_eliminar"):
        assert getattr(efectivos_op["consultar"], op) is False
    assert efectivos_op["borradores"].puede_crear is True  # activo, intacto
    # El admin conserva la gestión para poder reactivar.
    assert efectivos_admin["corpus"].puede_leer is True


async def test_resolver_rol_sin_modulo_deniega():
    repo = FakePermisoRepo()
    supervisor = _usuario(id=2, rol="supervisor")

    efectivos = await resolver_permisos_usuario.execute(repo, supervisor.id or 0, supervisor.rol)

    # supervisor genera/edita borradores pero no elimina
    assert efectivos["borradores"].puede_crear is True
    assert efectivos["borradores"].puede_eliminar is False
    # supervisor tambien gestiona sus chats del asistente (capacidad embebida)
    assert efectivos["chats"].puede_crear is True
    assert efectivos["chats"].puede_leer is True
    # un modulo que el supervisor no tiene en la matriz no se resuelve
    assert "sala_control" not in efectivos


# --- asignar_permisos_usuario ---


async def test_asignar_reemplaza_overrides():
    repo = FakePermisoRepo()
    operador = _usuario(id=1, rol="operador_juridico")
    auth = FakeAuthRepo([operador])

    await asignar_permisos_usuario.execute(
        permiso_repo=repo,
        auth_repo=auth,
        usuario_id=1,
        permisos={"consultar": PermisoCRUD(puede_leer=False)},
    )

    assert repo.overrides[1]["consultar"].puede_leer is False


async def test_asignar_permisos_vacios_borra_todo():
    repo = FakePermisoRepo(overrides={1: {"consultar": PermisoCRUD(puede_leer=False)}})
    operador = _usuario(id=1, rol="operador_juridico")
    auth = FakeAuthRepo([operador])

    await asignar_permisos_usuario.execute(
        permiso_repo=repo, auth_repo=auth, usuario_id=1, permisos={}
    )

    assert repo.overrides[1] == {}


async def test_asignar_target_admin_rechazado():
    repo = FakePermisoRepo()
    admin = make_admin(id=1)
    auth = FakeAuthRepo([admin])

    with pytest.raises(asignar_permisos_usuario.UsuarioAdministradorNoModificableError):
        await asignar_permisos_usuario.execute(
            permiso_repo=repo,
            auth_repo=auth,
            usuario_id=1,
            permisos={"consultar": PermisoCRUD(puede_leer=False)},
        )


async def test_asignar_usuario_inexistente():
    repo = FakePermisoRepo()
    auth = FakeAuthRepo([])

    with pytest.raises(asignar_permisos_usuario.UsuarioNoEncontradoError):
        await asignar_permisos_usuario.execute(
            permiso_repo=repo, auth_repo=auth, usuario_id=999, permisos={}
        )


async def test_asignar_modulo_desconocido():
    repo = FakePermisoRepo()
    operador = _usuario(id=1, rol="operador_juridico")
    auth = FakeAuthRepo([operador])

    with pytest.raises(asignar_permisos_usuario.ModuloNoEncontradoError):
        await asignar_permisos_usuario.execute(
            permiso_repo=repo,
            auth_repo=auth,
            usuario_id=1,
            permisos={"modulo_inexistente": PermisoCRUD(puede_leer=True)},
        )


# --- listar_permisos_usuario ---


async def test_listar_permisos_incluye_override_y_efectivo():
    repo = FakePermisoRepo(overrides={1: {"consultar": PermisoCRUD(puede_leer=False)}})
    operador = _usuario(id=1, rol="operador_juridico")
    auth = FakeAuthRepo([operador])

    detalle = await listar_permisos_usuario.execute(
        permiso_repo=repo, auth_repo=auth, usuario_id=1, rol="operador_juridico"
    )

    consultar = next(d for d in detalle if d.clave == "consultar")
    assert consultar.override.puede_leer is False
    assert consultar.efectivo.puede_leer is False
    assert consultar.default_rol.puede_leer is True  # el override no altera el default
    borradores = next(d for d in detalle if d.clave == "borradores")
    assert borradores.efectivo.puede_crear is True  # default del rol


async def test_listar_permisos_usuario_inexistente():
    repo = FakePermisoRepo()
    auth = FakeAuthRepo([])

    with pytest.raises(ValueError):
        await listar_permisos_usuario.execute(
            permiso_repo=repo, auth_repo=auth, usuario_id=999, rol="operador_juridico"
        )


# --- mis_permisos (sidebar usuario logueado) ---


async def test_mis_permisos_filtra_modulos_inactivos_y_sin_acceso():
    repo = FakePermisoRepo(
        modulos=[
            Modulo(clave="consultar", nombre="Consultar", descripcion="", ruta="/x", orden=1),
            Modulo(
                clave="borradores",
                nombre="Borradores",
                descripcion="",
                ruta="/y",
                orden=2,
                activo=False,
            ),
        ]
    )
    operador = _usuario(id=1, rol="operador_juridico")

    modulos = await mis_permisos.execute(repo, operador.id or 0, operador.rol)

    claves = [m.clave for m in modulos]
    assert "consultar" in claves  # activo + permiso
    assert "borradores" not in claves  # inactivo, fuera del sidebar


async def test_mis_permisos_admin_ve_gestion_full_y_consulta_denegada():
    repo = FakePermisoRepo()
    admin = make_admin(id=1)

    modulos = await mis_permisos.execute(repo, admin.id or 0, admin.rol)

    # El admin ve corpus (gestión) full; la consulta queda sin acceso de lectura.
    corpus = next(m for m in modulos if m.clave == "corpus")
    assert corpus.efectivo.puede_crear is True
    assert corpus.efectivo.puede_leer is True
    consultar = next(m for m in modulos if m.clave == "consultar")
    assert consultar.efectivo.puede_leer is False


# --- modulos_visibles ---


async def test_modulos_visibles_aplica_overrides_por_usuario_y_defaults_por_rol():
    # El operador 1 perdió "consultar" por override; el 2 no tiene overrides.
    repo = FakePermisoRepo(overrides={1: {"consultar": PermisoCRUD(puede_leer=False)}})
    auth = FakeAuthRepo(
        [
            _usuario(id=1, carnet="op1", rol="operador_juridico"),
            _usuario(id=2, carnet="op2", rol="operador_juridico"),
        ]
    )

    dto = await modulos_visibles.execute(repo, auth)

    claves = {c: [m.clave for m in ms] for c, ms in dto.por_usuario.items()}
    assert "consultar" not in claves["op1"]
    assert "consultar" in claves["op2"]
    # Un usuario nuevo del rol ve los defaults (sin overrides).
    assert "consultar" in [m.clave for m in dto.por_rol["operador_juridico"]]
    # corpus es de gestión: el operador no lo ve por defecto.
    assert "corpus" not in claves["op2"]
