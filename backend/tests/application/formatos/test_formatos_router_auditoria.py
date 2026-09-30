"""Promover, importar y eliminar bloques de un formato se auditan (R6, F-31).

Promover un formato lo hace canonico (semilla del tipo) y degrada al anterior;
importar puede sobrescribir formatos en masa; eliminar un bloque es destructivo.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario
from src.main import app

SUPERVISOR = Usuario(
    id=3,
    nombre="Sup",
    carnet="6000003",
    password_hash="x",
    rol="supervisor",
    activo=True,
    cargo="Vocal Relator",
)
ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Otro",
)


def _formato() -> SimpleNamespace:
    return SimpleNamespace(
        id=4,
        tipo_documento="auto_vista",
        slug="auto-1",
        autor="aliaga",
        engine="x",
        estado="canonico",
        version=2,
        meta={},
        bloques=[],
        esqueleto=None,
        hash_fuente="h",
        created_at=None,
        updated_at=None,
    )


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _preparar(usuario: Usuario, repo: MagicMock) -> MagicMock:
    app.dependency_overrides[deps.get_current_user] = lambda: usuario
    app.dependency_overrides[deps.get_formato_repo_dep] = lambda: repo
    audit = MagicMock()
    audit.registrar = AsyncMock()
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: audit
    return audit


def test_promover_formato_se_audita(client: TestClient) -> None:
    formato = _formato()
    repo = MagicMock(
        obtener=AsyncMock(return_value=formato),
        listar=AsyncMock(return_value=([], 0)),
        actualizar=AsyncMock(side_effect=lambda f: f),
    )
    audit = _preparar(SUPERVISOR, repo)

    assert client.post("/admin/formatos/4/promover").status_code == 200

    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.usuario_id, r.entidad, r.entidad_id) == (
        "promover_formato",
        SUPERVISOR.id,
        "formato",
        4,
    )


def test_eliminar_bloque_de_formato_se_audita(client: TestClient) -> None:
    formato = _formato()
    formato.bloques = [{"page": 1, "index": 0}]
    repo = MagicMock(
        obtener=AsyncMock(return_value=formato), actualizar=AsyncMock(side_effect=lambda f: f)
    )
    audit = _preparar(SUPERVISOR, repo)

    assert client.delete("/admin/formatos/4/bloques/p1:i0").status_code == 200

    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.entidad_id, r.detalle) == (
        "eliminar_bloque_formato",
        4,
        {"block_key": "p1:i0"},
    )


def test_importar_formatos_se_audita_con_el_resumen(client: TestClient, tmp_path) -> None:
    repo = MagicMock()
    audit = _preparar(ADMIN, repo)
    # el importador de la ruta vacia devuelve {importados: 0, omitidos: 0, total: 0}

    resp = client.post("/admin/formatos/importar", params={"vault_path": str(tmp_path)})

    assert resp.status_code == 200
    r = audit.registrar.await_args.args[0]
    assert r.accion == "importar_formatos"
    assert r.detalle == {"importados": 0, "omitidos": 0, "total": 0}
