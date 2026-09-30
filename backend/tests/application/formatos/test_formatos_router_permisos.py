"""Solo supervisor y administrador administran formatos; el operador recibe 403."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario
from src.main import app

OPERADOR = Usuario(
    id=5,
    nombre="Op",
    carnet="8012345",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Fiscal",
)


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    app.dependency_overrides[deps.get_formato_repo_dep] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("get", "/admin/formatos", None),
        ("get", "/admin/formatos/1", None),
        ("patch", "/admin/formatos/1/bloques/reordenar", {"orden": ["p0:i0"]}),
        ("delete", "/admin/formatos/1/bloques/p0:i0", None),
        ("patch", "/admin/formatos/1/configuracion", {"font": "Arial"}),
        ("post", "/admin/formatos/1/promover", None),
    ],
)
def test_el_operador_no_administra_formatos(client, metodo, ruta, cuerpo) -> None:
    resp = getattr(client, metodo)(ruta, **({"json": cuerpo} if cuerpo else {}))

    assert resp.status_code == 403
