"""Tests HTTP de /jobs: estado y cancelacion de trabajos de indexado.

TDD con TestClient y dependency_overrides: no toca DB ni Qdrant. Los trabajos
se inyectan directo en el registro porque un test sincrono no tiene event loop
(el camino real — lanzar y cancelar un trabajo que corre — esta cubierto en
tests/application/test_trabajos_indexado.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.services.trabajos_indexado import (
    EstadoJob,
    Job,
    TokenCancelacion,
    registro,
)
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
    yield TestClient(app)
    app.dependency_overrides.clear()
    registro._jobs.clear()  # noqa: SLF001 — limpieza del registro singleton


def _inyectar_job(
    job_id: str = "j1",
    *,
    usuario_id: int = OPERADOR.id,
    estado: EstadoJob = EstadoJob.EN_CURSO,
) -> Job:
    job = Job(
        id=job_id,
        tipo="norma",
        usuario_id=usuario_id,
        token=TokenCancelacion(),
        iniciado_en=datetime.now(UTC),
        estado=estado,
    )
    registro._jobs[job_id] = job  # noqa: SLF001 — sin loop no se puede `lanzar`
    return job


def test_job_desconocido_devuelve_404(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    assert client.get("/jobs/no-existe").status_code == 404
    assert client.post("/jobs/no-existe/cancel").status_code == 404


def test_el_dueno_ve_el_estado_de_su_trabajo(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    _inyectar_job()

    resp = client.get("/jobs/j1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "j1"
    assert resp.json()["estado"] == "en_curso"


def test_el_trabajo_de_otro_no_se_revela(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    _inyectar_job(usuario_id=ADMIN.id)

    assert client.get("/jobs/j1").status_code == 404
    assert client.post("/jobs/j1/cancel").status_code == 404


def test_un_administrador_si_ve_y_cancela_el_de_otro(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    job = _inyectar_job()

    assert client.get("/jobs/j1").status_code == 200
    resp = client.post("/jobs/j1/cancel")

    assert resp.status_code == 200
    # Sin tarea corriendo el trabajo no pasa a "cancelado" todavia: queda
    # pedida la cancelacion y se detiene en el proximo punto de control.
    assert resp.json()["cancelacion_solicitada"] is True
    assert job.token.cancelado is True


def test_cancelar_como_dueno(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    job = _inyectar_job()

    resp = client.post("/jobs/j1/cancel")

    assert resp.status_code == 200
    # Sin tarea corriendo el trabajo no pasa a "cancelado" todavia: queda
    # pedida la cancelacion y se detiene en el proximo punto de control.
    assert resp.json()["cancelacion_solicitada"] is True
    assert job.token.cancelado is True


def test_cancelar_un_trabajo_ya_terminado_da_409(client: TestClient):
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    _inyectar_job(estado=EstadoJob.COMPLETADO)

    resp = client.post("/jobs/j1/cancel")

    assert resp.status_code == 409
    assert "termino" in resp.json()["detail"]
