"""Endpoints de moderación de recomendaciones de doctrina (solo supervisor)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario
from src.main import app


def _usuario(rol: str, cargo: str) -> Usuario:
    return Usuario(
        id=9, nombre="U", carnet="8000001", password_hash="x", rol=rol, activo=True, cargo=cargo
    )


SUPERVISOR = _usuario("supervisor", "Vocal Presidente")
OPERADOR = _usuario("operador_juridico", "Fiscal")


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.aprobar = AsyncMock()
    r.rechazar = AsyncMock()
    r.aprobar_todas = AsyncMock(return_value=2)
    return r


def _cliente(usuario: Usuario, repo: MagicMock) -> TestClient:
    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    app.dependency_overrides[deps.get_current_user] = lambda: usuario
    app.dependency_overrides[deps.get_recomendacion_repo_dep] = lambda: repo
    return TestClient(app)


@pytest.fixture(autouse=True)
def _limpiar():
    yield
    app.dependency_overrides.clear()


def test_aprobar_recomendacion_pendiente(repo) -> None:
    repo.aprobar.return_value = SimpleNamespace(id=4, estado="recomendada")

    resp = _cliente(SUPERVISOR, repo).post("/doctrina/recomendaciones/4/aprobar")

    assert resp.status_code == 200
    assert resp.json() == {"recomendacion_id": 4, "estado": "recomendada"}
    repo.aprobar.assert_awaited_once_with(4, SUPERVISOR.id)


def test_aprobar_recomendacion_inexistente_o_no_pendiente_es_404(repo) -> None:
    repo.aprobar.return_value = None

    resp = _cliente(SUPERVISOR, repo).post("/doctrina/recomendaciones/4/aprobar")

    assert resp.status_code == 404


def test_rechazar_recomendacion_guarda_el_motivo(repo) -> None:
    repo.rechazar.return_value = SimpleNamespace(id=4, estado="rechazada")

    resp = _cliente(SUPERVISOR, repo).post(
        "/doctrina/recomendaciones/4/rechazar", json={"motivo": "No aplica al caso"}
    )

    assert resp.status_code == 200
    repo.rechazar.assert_awaited_once_with(4, SUPERVISOR.id, "No aplica al caso")


def test_aprobar_todas_sin_cuerpo_aprueba_todas_y_con_ids_solo_esas(repo) -> None:
    cliente = _cliente(SUPERVISOR, repo)

    assert cliente.post("/doctrina/recomendaciones/aprobar-todas").json() == {"aprobadas": 2}
    repo.aprobar_todas.assert_awaited_with(SUPERVISOR.id, ids=None)

    cliente.post("/doctrina/recomendaciones/aprobar-todas", json=[1, 3])
    repo.aprobar_todas.assert_awaited_with(SUPERVISOR.id, ids=[1, 3])


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("post", "/doctrina/recomendaciones/4/aprobar", None),
        ("post", "/doctrina/recomendaciones/4/rechazar", {"motivo": "No aplica al caso"}),
        ("post", "/doctrina/recomendaciones/aprobar-todas", None),
    ],
)
def test_el_operador_no_puede_moderar_recomendaciones(repo, metodo, ruta, cuerpo) -> None:
    resp = getattr(_cliente(OPERADOR, repo), metodo)(ruta, json=cuerpo)

    assert resp.status_code == 403
    repo.aprobar.assert_not_awaited()
    repo.rechazar.assert_not_awaited()
    repo.aprobar_todas.assert_not_awaited()
