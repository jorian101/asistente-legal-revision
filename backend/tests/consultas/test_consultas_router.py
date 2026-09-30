"""Tests HTTP del router /consultas (Fase 1.8 Sprint 3) + Regla 4/D4.

TDD con TestClient y dependency_overrides: no toca DB ni Qdrant.
Reemplaza las dependencias de auth (get_current_user -> require_consulta_user)
y el PipelineRAG/HistorialRepo por fakes. Verifica contrato HTTP y authz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario
from src.main import app as fastapi_app

ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Otro",
)
SUPERVISOR = Usuario(
    id=2,
    nombre="Supervisor",
    carnet="6000002",
    password_hash="x",
    rol="supervisor",
    activo=True,
    cargo="Vocal Relator",
)
OPERADOR = Usuario(
    id=3,
    nombre="Operador",
    carnet="8012345",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Fiscal",
)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def _make_fragmento_stub(qid: str = "abc") -> MagicMock:
    f = MagicMock()
    f.id = 1
    f.norma_id = 10
    f.obra_id = None
    f.expediente_id = None
    f.qdrant_point_id = qid
    f.texto = "Articulo 1. Probando..."
    f.padre_ref_key = None
    f.nivel_jerarquico = 4
    return f


def _make_contexto_stub() -> MagicMock:
    c = MagicMock()
    c.fragmentos = (_make_fragmento_stub(),)
    c.scores = (0.9,)
    c.tipo_respuesta = "consulta_simple"
    c.expediente_id = None
    c.latencia_ms = 42
    return c


@dataclass
class _FakeHistorial:
    id: int
    expediente_id: int | None
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    latencia_ms: int | None
    modelo_llm: str | None
    created_at: datetime | None


def _override_pipeline(contexto: Any | None = None, error: Exception | None = None) -> None:
    """Override del PipelineRAGDep con un fake que devuelve el contexto."""
    fake = MagicMock()
    if error is not None:
        fake.ejecutar = AsyncMock(side_effect=error)
    else:
        fake.ejecutar = AsyncMock(return_value=contexto)
    fastapi_app.dependency_overrides[deps.get_pipeline_rag_dep] = lambda: fake


def _override_historial_repo(items: list[_FakeHistorial], total: int) -> None:
    fake = MagicMock()
    fake.guardar = AsyncMock(
        side_effect=lambda h: _FakeHistorial(
            id=99,
            expediente_id=h.expediente_id,
            pregunta=h.pregunta,
            respuesta=h.respuesta,
            tipo_respuesta=h.tipo_respuesta,
            latencia_ms=h.latencia_ms,
            modelo_llm=h.modelo_llm,
            created_at=datetime(2026, 8, 4),
        )
    )
    fake.listar_por_usuario = AsyncMock(return_value=(items, total))
    fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: fake


def _override_current_user(user: Usuario | None) -> None:
    if user is None:
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: _raise_401()
    else:
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: user


def _raise_401():
    from fastapi import HTTPException, status

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


# ----- POST /consultas/ --------------------------------------------


def test_consulta_requiere_auth(client: TestClient) -> None:
    """Sin auth -> 401."""
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([], 0)
    _override_current_user(None)
    resp = client.post("/consultas/", json={"consulta": "hola"})
    assert resp.status_code == 401


def test_admin_no_puede_consultar(client: TestClient) -> None:
    """D4: administrador -> 403 (no tiene permiso 'consultar:crear')."""
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([], 0)
    _override_current_user(ADMIN)
    resp = client.post("/consultas/", json={"consulta": "hola"})
    assert resp.status_code == 403
    assert "permiso" in resp.json()["detail"].lower()


def test_supervisor_puede_consultar(client: TestClient) -> None:
    """Supervisor -> 200 con ContextoRecuperadoDTO."""
    contexto = _make_contexto_stub()
    _override_pipeline(contexto)
    _override_historial_repo([], 0)
    _override_current_user(SUPERVISOR)
    resp = client.post(
        "/consultas/",
        json={"consulta": "Cual es el plazo de apelacion?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tipo_respuesta"] == "consulta_simple"
    assert body["historial_id"] == 99
    assert len(body["fragmentos"]) == 1
    assert body["latencia_ms"] == 42


def test_operador_puede_consultar(client: TestClient) -> None:
    """Operador juridico -> 200."""
    contexto = _make_contexto_stub()
    _override_pipeline(contexto)
    _override_historial_repo([], 0)
    _override_current_user(OPERADOR)
    resp = client.post("/consultas/", json={"consulta": "consulta legal"})
    assert resp.status_code == 200


def test_consulta_sin_expediente_devuelve_422(client: TestClient) -> None:
    """Auto_vista_* sin expediente_id -> 422 con mensaje claro."""
    from src.domain.exceptions import ConsultaSinExpedienteError

    _override_pipeline(error=ConsultaSinExpedienteError("requiere"))
    _override_historial_repo([], 0)
    _override_current_user(SUPERVISOR)
    resp = client.post(
        "/consultas/",
        json={"consulta": "Dictar auto de vista", "expediente_id": None},
    )
    assert resp.status_code == 422


def test_variante_restringida_no_soportada_422(client: TestClient) -> None:
    """Apelación restringida sin plantilla propia -> 422 descriptivo.

    La SAC es competente para esa vía, así que el error no debe ser
    FaltaCompetenciaError: se informa que falta la variante."""
    from src.domain.exceptions import VarianteApelacionNoSoportadaError

    _override_pipeline(
        error=VarianteApelacionNoSoportadaError("apelación restringida sin plantilla")
    )
    _override_historial_repo([], 0)
    _override_current_user(SUPERVISOR)
    resp = client.post(
        "/consultas/",
        json={"consulta": "Dictar auto de vista", "expediente_id": 8},
    )
    assert resp.status_code == 422
    assert "restringida" in resp.json()["detail"]


def test_consulta_con_body_invalido_422(client: TestClient) -> None:
    """consulta con menos de 3 chars -> 422 (validacion Pydantic)."""
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([], 0)
    _override_current_user(SUPERVISOR)
    resp = client.post("/consultas/", json={"consulta": "ab"})
    assert resp.status_code == 422


# ----- GET /consultas/historial ------------------------------------


def test_historial_requiere_auth(client: TestClient) -> None:
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([], 0)
    _override_current_user(None)
    resp = client.get("/consultas/historial")
    assert resp.status_code == 401


def test_historial_admin_bloqueado(client: TestClient) -> None:
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([], 0)
    _override_current_user(ADMIN)
    resp = client.get("/consultas/historial")
    assert resp.status_code == 403


def test_historial_supervisor_retorna_200(client: TestClient) -> None:
    item = _FakeHistorial(
        id=5,
        expediente_id=None,
        pregunta="x",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        latencia_ms=100,
        modelo_llm=None,
        created_at=datetime(2026, 8, 4),
    )
    _override_pipeline(_make_contexto_stub())
    _override_historial_repo([item], total=1)
    _override_current_user(SUPERVISOR)
    resp = client.get("/consultas/historial")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["pregunta"] == "x"


def test_historial_usa_usuario_del_jwt_no_de_query(client: TestClient) -> None:
    """Regla 4: el listado filtra por usuario del JWT, no por query."""
    _override_pipeline(_make_contexto_stub())
    _override_historical_empty()
    _override_current_user(SUPERVISOR)
    resp = client.get("/consultas/historial")
    assert resp.status_code == 200
    call = fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep]()
    # El repo fue llamado con usuario_id=2 (SUPERVISOR.id), no con nada del query.
    listar_call = call.listar_por_usuario.await_args
    assert listar_call.kwargs["usuario_id"] == SUPERVISOR.id


def _override_historical_empty() -> None:
    fake = MagicMock()
    fake.guardar = AsyncMock()
    fake.listar_por_usuario = AsyncMock(return_value=([], 0))
    fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: fake


def _override_repos_expediente_y_obras() -> None:
    """Overrides de expediente_repo/obra_repo (Fase 5b) con fakes vacíos."""
    exp_repo = MagicMock()
    exp_repo.obtener = AsyncMock(return_value=None)
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: exp_repo

    obra_repo = MagicMock()
    obra_repo.listar_por_expediente = AsyncMock(return_value=[])
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo


def _make_contexto_expandido_rico() -> Any:
    """ContextoExpandido real con fragmento rico (hechos+norma+vicio)."""
    from src.domain.entities.fragmento import Fragmento
    from src.domain.value_objects.contexto_expandido import ContextoExpandido

    frag = Fragmento(
        id=1,
        norma_id=10,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id="pt-rich",
        texto=(
            "El procesado compareció ante el juez y declaró bajo juramento "
            "en foja 5. El CPPM Art. 361 establece nulidad por notificación "
            "defectuosa. El procesado no fue notificado, causándole "
            "indefensión procesal."
        ),
        padre_ref_id=None,
        padre_ref_key="CPPM_361",
        nivel_jerarquico=4,
        metadatos={"tipo_chunk": "articulo_simple"},
        tipo_chunk="articulo_simple",
    )
    return ContextoExpandido(
        fragmentos_con_padres=(frag,),
        scores=(0.9,),
        query_original="x",
        tipo_respuesta="auto_vista_consulta",
        expediente_id=7,
        breadcrumbs=(("root", "pt-rich"),),
    )


def test_sugerir_argumentacion_devuelve_sugerencia(client: TestClient) -> None:
    """Fase 5b (G4): POST /consultas/sugerir-argumentacion devuelve JSON estructurado."""
    _override_pipeline(_make_contexto_expandido_rico())
    _override_repos_expediente_y_obras()
    _override_current_user(OPERADOR)
    resp = client.post(
        "/consultas/sugerir-argumentacion",
        json={"consulta": "analizar vicios", "expediente_id": 7},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tipo_respuesta"] == "auto_vista_consulta"
    assert body["total_bloques"] >= 3
    assert len(body["fundamentos_hecho"]) >= 1
    assert len(body["fundamentos_derecho"]) >= 1
    assert len(body["vicios_sanear"]) >= 1
    assert len(body["resumen_ejecutivo"]) > 10
    # Estructura de un bloque
    bloque = body["fundamentos_hecho"][0]
    assert set(bloque.keys()) == {
        "titulo",
        "tipo",
        "contenido",
        "fojas_referidas",
        "normas_citadas",
        "prioridad",
    }


def test_sugerir_argumentacion_requiere_auth(client: TestClient) -> None:
    """Fase 5b: sin token válido -> 401."""
    _override_pipeline(_make_contexto_expandido_rico())
    _override_repos_expediente_y_obras()
    _override_current_user(None)
    resp = client.post(
        "/consultas/sugerir-argumentacion",
        json={"consulta": "x", "expediente_id": 7},
    )
    assert resp.status_code == 401


def test_sugerir_argumentacion_bloquea_admin(client: TestClient) -> None:
    """Fase 5b (Regla 4/D4): administrador no puede usar consultas."""
    _override_pipeline(_make_contexto_expandido_rico())
    _override_repos_expediente_y_obras()
    _override_current_user(ADMIN)
    resp = client.post(
        "/consultas/sugerir-argumentacion",
        json={"consulta": "x", "expediente_id": 7},
    )
    assert resp.status_code == 403


def _override_historial_delete(resultado: bool) -> MagicMock:
    """Override del repo de historial con eliminar_soft."""
    fake = MagicMock()
    fake.eliminar_soft = AsyncMock(return_value=resultado)
    fake.listar_por_usuario = AsyncMock(return_value=([], 0))
    fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: fake
    return fake


def test_eliminar_historial_204_soft_delete(client: TestClient) -> None:
    """CRITICAL #4: DELETE /consultas/historial/{id} -> 204 (soft delete)."""
    _override_current_user(OPERADOR)
    fake = _override_historial_delete(resultado=True)

    resp = client.delete("/consultas/historial/42")

    assert resp.status_code == 204
    fake.eliminar_soft.assert_awaited_once_with(historial_id=42, usuario_id=OPERADOR.id)


def test_eliminar_historial_404_si_no_es_propio(client: TestClient) -> None:
    """Regla 4: entrada de otro usuario / inexistente -> 404."""
    _override_current_user(OPERADOR)
    _override_historial_delete(resultado=False)

    resp = client.delete("/consultas/historial/99")

    assert resp.status_code == 404


def test_eliminar_historial_requiere_auth(client: TestClient) -> None:
    """Sin token valido -> 401."""
    _override_current_user(None)

    resp = client.delete("/consultas/historial/1")

    assert resp.status_code == 401


# ===== GET /consultas/historial/{id}/fuentes (citas RAG, Regla 4) =====


def _historial_propio(historial_id: int, usuario_id: int):
    from src.domain.entities.consulta_historial import ConsultaHistorial

    return ConsultaHistorial(
        id=historial_id,
        expediente_id=None,
        usuario_id=usuario_id,
        pregunta="test",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas={
            "fragmentos": [
                {
                    "id": 5,
                    "norma_id": 1,
                    "obra_id": None,
                    "texto": "Art. 140 CPM",
                    "padre_ref_key": "LOJM_3_MASTER",
                    "nivel_jerarquico": 4,
                }
            ],
            "scores": [0.9],
        },
        latencia_ms=100,
        modelo_llm=None,
    )


def _override_enrich_repos(app) -> None:
    """Fakes de los repos de enriquecimiento de /fuentes (sin DB).

    El endpoint ahora depende de norma/obra/expediente repo; sin override
    FastAPI resolveria la dep real y abriria sesion de BD (cuelga el test).
    Devolver None/{}/ -> los campos enriquecidos quedan None (caso base).
    """
    from src.adapters.http import dependencies as deps

    norma_repo = MagicMock()
    norma_repo.get_by_id = AsyncMock(return_value=None)
    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})
    exp_repo = MagicMock()
    exp_repo.obtener = AsyncMock(return_value=None)
    app.dependency_overrides[deps.get_norma_repo] = lambda: norma_repo
    app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo
    app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: exp_repo


def test_fuentes_200_devuelve_citas_sanitizadas(client: TestClient) -> None:
    from src.adapters.http import dependencies as deps
    from src.main import app

    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=_historial_propio(87, 2))
    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo
    _override_enrich_repos(app)

    response = client.get("/consultas/historial/87/fuentes")

    assert response.status_code == 200
    data = response.json()
    assert len(data["fragmentos"]) == 1
    assert data["fragmentos"][0]["referencia"] == "LOJM 3"
    assert data["scores"] == [0.9]
    # Regla 4: el filtro por usuario llega al repo (posicional).
    args = repo.obtener_por_id.await_args.args
    assert args == (87, OPERADOR.id)


def test_fuentes_404_si_no_es_propia(client: TestClient) -> None:
    """Entrada ajena o inexistente -> 404 encubierto (no revela cual)."""
    from src.adapters.http import dependencies as deps
    from src.main import app

    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=None)
    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo
    _override_enrich_repos(app)

    response = client.get("/consultas/historial/999/fuentes")

    assert response.status_code == 404


# ----- GET /consultas/historial/{id} (reanudación tras recarga) -----


def _historial_detalle_repo(historial=None):
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=historial)
    return repo


def _historial_stub(respuesta="texto final", estado="completado"):
    from src.domain.entities.consulta_historial import ConsultaHistorial

    return ConsultaHistorial(
        id=99,
        expediente_id=7,
        usuario_id=3,
        pregunta="hola",
        respuesta=respuesta,
        tipo_respuesta="consulta_simple",
        estado=estado,
        fuentes_recuperadas={},
        latencia_ms=10,
        modelo_llm="m",
    )


def _override_consulta_user(usuario: Usuario) -> None:
    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario


def test_historial_detalle_propio_200(client: TestClient) -> None:
    _override_consulta_user(OPERADOR)
    fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: (
        _historial_detalle_repo(_historial_stub())
    )

    resp = client.get("/consultas/historial/99")

    assert resp.status_code == 200
    body = resp.json()
    assert body["respuesta"] == "texto final"
    assert body["estado"] == "completado"


def test_historial_detalle_ajeno_404(client: TestClient) -> None:
    _override_consulta_user(OPERADOR)
    fastapi_app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: (
        _historial_detalle_repo(None)
    )

    resp = client.get("/consultas/historial/99")

    assert resp.status_code == 404
