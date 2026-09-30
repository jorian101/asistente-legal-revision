"""Los cambios de permisos y de modulos se auditan (R6, F-31).

Asignar permisos a un usuario o habilitar/deshabilitar un modulo cambia quien puede
hacer que: es la accion mas sensible del panel admin y no dejaba rastro.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.permiso import TODAS_LAS_CLAVES, Modulo
from src.domain.entities.usuario import Usuario
from src.main import app

ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Otro",
)
OPERADOR = Usuario(
    id=5,
    nombre="Op",
    carnet="8012345",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Fiscal",
)


class _PermisoRepo:
    def __init__(self) -> None:
        self.modulos = [
            Modulo(clave=c, nombre=c, descripcion="", ruta=f"/{c}", orden=i, activo=True)
            for i, c in enumerate(sorted(TODAS_LAS_CLAVES))
        ]

    async def listar_modulos(self) -> list[Modulo]:
        return self.modulos

    async def get_permisos_usuario(self, usuario_id: int) -> dict:
        return {}

    async def reemplazar_permisos_usuario(self, usuario_id: int, permisos: dict) -> None:
        return None

    async def actualizar_modulo(self, clave: str, **campos) -> Modulo:
        return Modulo(clave=clave, nombre="Nuevo", descripcion="", ruta="/x", orden=1, activo=False)


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_permiso_repo_dep] = lambda: _PermisoRepo()
    auth = MagicMock()
    auth.get_by_carnet = AsyncMock(return_value=OPERADOR)
    auth.get_by_id = AsyncMock(return_value=OPERADOR)
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth
    yield TestClient(app)
    app.dependency_overrides.clear()


def _audit(falla: bool = False) -> MagicMock:
    fake = MagicMock()
    fake.registrar = AsyncMock(side_effect=RuntimeError("bd caida") if falla else None)
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: fake
    return fake


def test_asignar_permisos_se_audita(client: TestClient) -> None:
    audit = _audit()

    resp = client.put(
        "/admin/usuarios/8012345/permisos",
        json={"permisos": {"obras": {"puede_leer": True, "puede_eliminar": False}}},
    )

    assert resp.status_code == 204
    registro = audit.registrar.await_args.args[0]
    assert registro.accion == "asignar_permisos"
    assert (registro.usuario_id, registro.entidad, registro.entidad_id) == (1, "usuario", 5)
    assert registro.detalle == {"carnet": "8012345", "modulos": ["obras"]}


def test_actualizar_modulo_se_audita(client: TestClient) -> None:
    audit = _audit()

    resp = client.patch("/admin/modulos/obras", json={"activo": False})

    assert resp.status_code == 200
    registro = audit.registrar.await_args.args[0]
    assert registro.accion == "actualizar_modulo"
    assert (registro.usuario_id, registro.entidad) == (1, "modulo")
    assert registro.detalle == {"clave": "obras", "campos": {"activo": False}}


def test_si_la_auditoria_falla_la_accion_igual_se_completa(client: TestClient) -> None:
    _audit(falla=True)

    resp = client.patch("/admin/modulos/obras", json={"activo": False})

    assert resp.status_code == 200


def test_modulos_visibles_por_usuario_y_por_rol(client: TestClient) -> None:
    auth = MagicMock()
    auth.listar_usuarios = AsyncMock(return_value=[OPERADOR])
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth

    resp = client.get("/admin/modulos-visibles")

    assert resp.status_code == 200
    body = resp.json()
    claves_op = {m["clave"] for m in body["por_usuario"]["8012345"]}
    assert "consultar" in claves_op
    assert "corpus" not in claves_op  # gestión: el operador no lo ve
    assert set(body["por_rol"]) == {"administrador", "supervisor", "operador_juridico"}
