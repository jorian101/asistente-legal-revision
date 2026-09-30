"""Tests del router de doctrina (Plan D — interfaz supervisor/operador).

Verifica que las acciones EXCLUSIVAS del supervisor (aprobar, rechazar,
cargar global, ver estados) requieran rol supervisor, no solo permiso CRUD.
El admin/operador con permiso 'actualizar' NO pueden aprobar/rechazar.

Sin DB, sin PyMuPDF. TestClient + dependency_overrides.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario
from src.main import app as fastapi_app
from tests._factories import make_supervisor, make_usuario


@pytest.fixture
def supervisor() -> Usuario:
    return make_supervisor(id=2)


@pytest.fixture
def operador() -> Usuario:
    return make_usuario(id=3)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def _override_auth(usuario: Usuario, *, auth_only: bool = False) -> None:
    """Override de current_user; si auth_only, las require_* aplican su policy."""
    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    if not auth_only:
        fastapi_app.dependency_overrides[deps.require_supervisor] = lambda: usuario


def _override_obra_repo() -> None:
    """Mock del ObraRepo para aprobar/rechazar (use case no toca DB)."""
    from src.domain.entities.obra import Obra

    obra = Obra(
        id=1,
        expediente_id=None,
        propietario_id=2,
        tipo_documento="doctrina",
        nombre_archivo="scp.pdf",
        contenido_texto="x",
        ruta_archivo=None,
        estado_visibilidad="publicado",
        fuente="generado_sistema",
        tamano_archivo=1,
        estado_procesamiento="completado",
        autor="TCP",
        procedencia="h",
        recomendada=False,
        activo=True,
    )
    repo = AsyncMock()
    repo.actualizar_visibilidad = AsyncMock(return_value=obra)
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: repo
    # Sin esto get_vector_repo abre un QdrantClient real (chequeo de version por red).
    vector_repo = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_vector_repo] = lambda: vector_repo


# --- Plan D (F2): las acciones de supervisor requieren rol supervisor ---


def test_descargar_puntero_404_honesto(client, supervisor) -> None:
    """Puntero N2/N3: 404 con mensaje (no .txt vacío)."""
    from types import SimpleNamespace

    _override_auth(supervisor, auth_only=True)
    repo = AsyncMock()
    repo.obtener = AsyncMock(
        return_value=SimpleNamespace(
            id=9,
            nombre_archivo="SCP-0623",
            ruta_archivo=None,
            contenido_texto="",
            corpus_ref="SCP-0623-2024-S4",
            corpus="jurisprudencia",
        )
    )
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: repo

    resp = client.get("/doctrina/obras/9/descargar")

    assert resp.status_code == 404
    assert "se consulta" in resp.json()["detail"]


def _override_editar_doctrina() -> AsyncMock:
    from types import SimpleNamespace

    repo = AsyncMock()
    repo.actualizar_detalles = AsyncMock(
        return_value=None
    )  # 404 basta para inspeccionar la llamada
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: repo
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: SimpleNamespace()
    return repo


def test_doctrina_events_exige_supervisor() -> None:
    """El SSE emite nombres de archivo y motivos de rechazo de todos: solo el supervisor (F-36).

    Se inspecciona la dependencia del endpoint en vez de abrir el stream (infinito).
    """
    from src.routers import doctrina as doctrina_router

    ruta = next(r for r in doctrina_router.router.routes if r.path == "/doctrina/events")  # type: ignore[attr-defined]
    dependencias = {d.call for d in ruta.dependant.dependencies}  # type: ignore[attr-defined]

    assert deps.require_supervisor in dependencias
