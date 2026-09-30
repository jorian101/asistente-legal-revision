"""Tests HTTP del router /admin/usuarios (HU-01 crear usuario).

Regresión: carnet duplicado debe responder 409 (CarnetDuplicadoError), no 500
(IntegrityError crudo del repo).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.auth.crear_usuario import CarnetDuplicadoError
from src.domain.entities.usuario import Usuario

ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Otro",
)

ADMIN_VALIDO = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Personal Técnico",
)


@pytest.fixture
def client():
    from src.main import app

    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    yield TestClient(app)
    app.dependency_overrides.clear()


def _crear_body() -> dict:
    return {
        "nombre": "QA Admin Test",
        "carnet": "qaadmin",
        "password": "password123",
        "rol": "operador_juridico",
        "cargo": "Auditor",
    }


def test_crear_usuario_carnet_duplicado_409(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.crear_usuario = AsyncMock(side_effect=CarnetDuplicadoError("carnet ya registrado"))
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo

    resp = client.post("/admin/usuarios", json=_crear_body())

    assert resp.status_code == 409, f"esperado 409, obtuvo {resp.status_code}"


def test_crear_usuario_ok_201(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    creado = ADMIN
    auth_repo.crear_usuario = AsyncMock(return_value=creado)
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo

    resp = client.post("/admin/usuarios", json=_crear_body())

    assert resp.status_code == 200, f"esperado 200, obtuvo {resp.status_code}"


def test_modificar_usuario_carnet_duplicado_409(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.get_by_carnet = AsyncMock(return_value=ADMIN_VALIDO)
    auth_repo.actualizar_usuario = AsyncMock(
        side_effect=CarnetDuplicadoError("carnet ya registrado")
    )
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo

    resp = client.patch(
        "/admin/usuarios/9000001",
        json={"nombre": "Nuevo Nombre", "carnet_nuevo": "9000002"},
    )

    assert resp.status_code == 409, f"esperado 409, obtuvo {resp.status_code}"


# --- Trail of Bits R6: la gestion de usuarios se audita ---


def _override_audit_repo() -> MagicMock:
    from src.main import app

    fake = MagicMock()
    fake.registrar = AsyncMock()
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: fake
    return fake


def _acciones(audit: MagicMock) -> list[str]:
    """Acciones auditadas, en orden (el repo recibe el VO posicionalmente)."""
    return [c.args[0].accion for c in audit.registrar.await_args_list]


def test_crear_usuario_audita_r6(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.crear_usuario = AsyncMock(return_value=ADMIN_VALIDO)
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo
    audit = _override_audit_repo()

    resp = client.post("/admin/usuarios", json=_crear_body())

    assert resp.status_code == 200
    assert _acciones(audit) == ["crear_usuario"]
    assert audit.registrar.await_args.args[0].usuario_id == ADMIN.id


def test_modificar_usuario_audita_r6(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.get_by_carnet = AsyncMock(return_value=ADMIN_VALIDO)
    auth_repo.actualizar_usuario = AsyncMock(return_value=ADMIN_VALIDO)
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo
    audit = _override_audit_repo()

    resp = client.patch("/admin/usuarios/9000001", json={"nombre": "Nuevo Nombre"})

    assert resp.status_code == 200
    assert _acciones(audit) == ["modificar_usuario"]


def test_reset_password_audita_r6_sin_password(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.get_by_carnet = AsyncMock(return_value=ADMIN_VALIDO)
    auth_repo.actualizar_usuario = AsyncMock()
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo
    audit = _override_audit_repo()

    resp = client.post(
        "/admin/usuarios/9000001/reset-password",
        json={"nueva_password": "otraPassword123"},
    )

    assert resp.status_code == 200
    assert _acciones(audit) == ["reset_password"]
    # RG5: la password jamas se persiste en el log de auditoria.
    detalle = audit.registrar.await_args.args[0].detalle
    assert "otraPassword123" not in str(detalle)


def test_desbloquear_2fa_audita_r6(client: TestClient) -> None:
    from src.main import app

    auth_repo = MagicMock()
    auth_repo.get_by_carnet = AsyncMock(return_value=ADMIN_VALIDO)
    auth_repo.desbloquear_2fa = AsyncMock()
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo
    audit = _override_audit_repo()

    resp = client.post("/admin/usuarios/9000001/desbloquear-2fa")

    assert resp.status_code == 200
    assert _acciones(audit) == ["desbloquear_2fa"]
