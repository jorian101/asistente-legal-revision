"""Tests F3.2: endpoints de corpus N2/N3 y recomendar por corpus.

Sin DB: TestClient + dependency_overrides (mismo patrón que
test_doctrina_router.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.norma import Norma
from src.domain.entities.usuario import Usuario
from src.main import app as fastapi_app
from tests._factories import make_supervisor


@pytest.fixture
def supervisor() -> Usuario:
    return make_supervisor(id=2)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def _norma(abreviatura: str, jerarquia: str) -> Norma:
    tipo = "scp_tcp" if jerarquia == "jurisprudencia" else "codigo_militar"
    if jerarquia == "doctrina":
        tipo = "doctrina_libro"
    if jerarquia == "suprema":
        tipo = "constitucion"
    return Norma(
        id=9,
        nombre=f"Nombre {abreviatura}",
        abreviatura=abreviatura,
        tipo=tipo,  # type: ignore[arg-type]
        jerarquia=jerarquia,  # type: ignore[arg-type]
        version=None,
        ruta_archivo=None,
        indexado=True,
        indexado_por=None,
        activo=True,
        created_at=None,
    )


def _override_auth(usuario: Usuario) -> None:
    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    fastapi_app.dependency_overrides[deps.require_supervisor] = lambda: usuario


def items(resp) -> list:
    return resp.json()


def test_recomendar_por_corpus_201_y_excluyentes_422(client, supervisor) -> None:
    """POST /recomendar acepta corpus+ref; mezcla con obra -> 422."""
    _override_auth(supervisor)
    reco_repo = AsyncMock()

    async def _recomendar(**kwargs):
        from src.domain.entities.recomendacion_doctrina import (
            RecomendacionDoctrina,
        )

        return RecomendacionDoctrina(
            id=5,
            obra_global_id=kwargs.get("obra_global_id"),
            expediente_id=kwargs["expediente_id"],
            recomendado_por=2,
            estado=kwargs["estado"],
            corpus=kwargs.get("corpus"),
            corpus_ref=kwargs.get("corpus_ref"),
        )

    reco_repo.recomendar = AsyncMock(side_effect=_recomendar)
    fastapi_app.dependency_overrides[deps.get_recomendacion_repo_dep] = lambda session=None: (
        reco_repo
    )
    obra_repo = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo
    norma_repo = AsyncMock()
    norma_repo.get_by_abreviatura = AsyncMock(
        return_value=_norma("LIB-ATIENZA-INTERP-2019", "doctrina")
    )
    fastapi_app.dependency_overrides[deps.get_norma_repo] = lambda: norma_repo
    expediente_repo = AsyncMock()
    expediente_repo.obtener = AsyncMock(return_value=SimpleNamespace(id=8, estado="activo"))
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda session=None: (
        expediente_repo
    )
    auth_repo = AsyncMock()
    auth_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(nombre="Vocal Test", cargo="Vocal")
    )
    fastapi_app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo

    resp = client.post(
        "/doctrina/recomendar",
        json={
            "expediente_id": 8,
            "corpus": "doctrina",
            "corpus_ref": "LIB-ATIENZA-INTERP-2019",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["corpus_ref"] == "LIB-ATIENZA-INTERP-2019"
    assert body["obra_global_id"] is None

    resp = client.post(
        "/doctrina/recomendar",
        json={
            "obra_global_id": 1,
            "expediente_id": 8,
            "corpus": "doctrina",
            "corpus_ref": "LIB-X",
        },
    )
    assert resp.status_code == 422


def _montar_recomendar(client, supervisor, norma):
    _override_auth(supervisor)
    reco_repo = AsyncMock()

    async def _recomendar(**kwargs):
        from src.domain.entities.recomendacion_doctrina import RecomendacionDoctrina

        return RecomendacionDoctrina(
            id=6,
            obra_global_id=None,
            expediente_id=kwargs["expediente_id"],
            recomendado_por=2,
            estado=kwargs["estado"],
            corpus=kwargs.get("corpus"),
            corpus_ref=kwargs.get("corpus_ref"),
        )

    reco_repo.recomendar = AsyncMock(side_effect=_recomendar)
    fastapi_app.dependency_overrides[deps.get_recomendacion_repo_dep] = lambda session=None: (
        reco_repo
    )
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: AsyncMock()
    norma_repo = AsyncMock()
    norma_repo.get_by_abreviatura = AsyncMock(return_value=norma)
    fastapi_app.dependency_overrides[deps.get_norma_repo] = lambda: norma_repo
    expediente_repo = AsyncMock()
    expediente_repo.obtener = AsyncMock(return_value=SimpleNamespace(id=8, estado="activo"))
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda session=None: (
        expediente_repo
    )
    auth_repo = AsyncMock()
    auth_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(nombre="Vocal", cargo="Vocal"))
    fastapi_app.dependency_overrides[deps.get_auth_repo] = lambda: auth_repo


def test_recomendar_una_norma_del_corpus(client, supervisor) -> None:
    """Las normas tambien se recomiendan al expediente."""
    _montar_recomendar(client, supervisor, _norma("CPE", "suprema"))

    resp = client.post(
        "/doctrina/recomendar",
        json={"expediente_id": 8, "corpus": "norma", "corpus_ref": "CPE"},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["corpus_ref"] == "CPE"


@pytest.mark.parametrize("estado", ["privado", "pendiente", "rechazado"])
def test_no_se_recomienda_una_fuente_que_no_es_global(client, supervisor, estado) -> None:
    norma = _norma("LIB-X", "doctrina")
    norma.estado_visibilidad = estado
    _montar_recomendar(client, supervisor, norma)

    resp = client.post(
        "/doctrina/recomendar",
        json={"expediente_id": 8, "corpus": "doctrina", "corpus_ref": "LIB-X"},
    )

    assert resp.status_code == 404
