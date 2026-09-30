"""Tests HTTP del router /admin/consultas/historial (Task 8b).

Verifica:
- 403 sin admin (operador juridico no accede).
- 200 con admin lista el historial con carnet/nombre del usuario.
- Los filtros (usuario, tipo, fechas, texto) se pasan al repo.
- DELETE soft delete admin (204) y 404 si no existe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.ports.consulta_historial_repo import ConsultaHistorialAdmin
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
OPERADOR = Usuario(
    id=2,
    nombre="Operador",
    carnet="8012345",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Fiscal",
)


@pytest.fixture
def client():
    from src.main import app

    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _item(
    *,
    historial_id: int = 1,
    usuario_id: int = 1,
    carnet: str = "9000001",
    nombre: str = "Admin",
) -> ConsultaHistorialAdmin:
    return ConsultaHistorialAdmin(
        id=historial_id,
        expediente_id=None,
        usuario_id=usuario_id,
        usuario_carnet=carnet,
        usuario_nombre=nombre,
        pregunta="¿Cómo proceder ante una radicatoria?",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        latencia_ms=195,
        modelo_llm=None,
        fuentes_recuperadas=None,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )


def test_historial_admin_403_si_no_es_admin(client: TestClient) -> None:
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/consultas/historial")

    assert response.status_code == 403


def test_historial_admin_200_retorna_items_con_usuario(client: TestClient) -> None:
    from src.main import app

    items = [
        _item(historial_id=1),
        _item(
            historial_id=2,
            usuario_id=29,
            carnet="qaop",
            nombre="QA Auditor Operador",
        ),
    ]
    repo = MagicMock()
    repo.listar_admin = AsyncMock(return_value=(items, 2))

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    response = client.get("/admin/consultas/historial")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["pagina"] == 1
    assert len(data["items"]) == 2
    item = data["items"][1]
    assert item["usuario_carnet"] == "qaop"
    assert item["usuario_nombre"] == "QA Auditor Operador"
    assert item["tipo_respuesta"] == "consulta_simple"


def test_historial_admin_pasa_filtros_al_repo(client: TestClient) -> None:
    from src.main import app

    repo = MagicMock()
    repo.listar_admin = AsyncMock(return_value=([], 0))

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    client.get(
        "/admin/consultas/historial"
        "?usuario_id=29&expediente_id=8&tipo_respuesta=consulta_simple"
        "&estado=en_progreso"
        "&fecha_desde=2026-08-01&fecha_hasta=2026-08-31&texto=radicatoria"
        "&pagina=2&por_pagina=25"
    )

    repo.listar_admin.assert_awaited_once()
    kwargs = repo.listar_admin.call_args.kwargs
    assert kwargs["usuario_id"] == 29
    assert kwargs["expediente_id"] == 8
    assert kwargs["tipo_respuesta"] == "consulta_simple"
    assert kwargs["estado"] == "en_progreso"
    assert kwargs["texto"] == "radicatoria"
    assert kwargs["fecha_desde"] is not None
    assert kwargs["fecha_hasta"] is not None
    assert kwargs["pagina"] == 2
    assert kwargs["por_pagina"] == 25


def test_historial_admin_delete_204(client: TestClient) -> None:
    from src.main import app

    repo = MagicMock()
    repo.eliminar_soft_admin = AsyncMock(return_value=True)

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    response = client.delete("/admin/consultas/historial/42")

    assert response.status_code == 204
    repo.eliminar_soft_admin.assert_awaited_once_with(historial_id=42)


def test_historial_admin_delete_404_si_no_existe(client: TestClient) -> None:
    from src.main import app

    repo = MagicMock()
    repo.eliminar_soft_admin = AsyncMock(return_value=False)

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    response = client.delete("/admin/consultas/historial/999")

    assert response.status_code == 404


def test_historial_admin_delete_403_si_no_es_admin(client: TestClient) -> None:
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.delete("/admin/consultas/historial/42")

    assert response.status_code == 403


def test_historial_admin_delete_se_audita(client: TestClient) -> None:
    """Borrar la consulta de OTRO usuario es una accion sensible (R6, F-31)."""
    from src.main import app

    repo = MagicMock()
    repo.eliminar_soft_admin = AsyncMock(return_value=True)
    audit = MagicMock()
    audit.registrar = AsyncMock()
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: audit

    assert client.delete("/admin/consultas/historial/42").status_code == 204

    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.usuario_id, r.entidad, r.entidad_id) == (
        "eliminar_consulta_admin",
        ADMIN.id,
        "consulta_historial",
        42,
    )
