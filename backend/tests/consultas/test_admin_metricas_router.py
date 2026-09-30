"""Tests HTTP del router /admin/metricas/contexto (HU-22, Sprint 5).

Verifica:
- 403 sin admin (operador juridico no puede acceder).
- 200 con admin retorna MetricasContextoDTO con promedios.
- Query param `limite` se pasa al use case.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.ports.consulta_historial_repo import ConsultaHistorialAdmin
from src.domain.entities.consulta_historial import ConsultaHistorial
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


def _historial_mock(
    *,
    consulta_id: int = 1,
    usuario_id: int = 1,
    expansion_realizada: bool = True,
    latencia_expansion_ms: int = 42,
    nodos_ascendidos: int = 4,
    breadcrumbs_count: int = 7,
) -> ConsultaHistorial:
    fuentes = {
        "tipo_respuesta": "consulta_simple",
        "expansion": {
            "realizada": expansion_realizada,
            "latencia_expansion_ms": latencia_expansion_ms,
            "nodos_ascendidos": nodos_ascendidos,
            "breadcrumbs_count": breadcrumbs_count,
        },
    }
    return ConsultaHistorial(
        id=consulta_id,
        expediente_id=None,
        usuario_id=usuario_id,
        pregunta="test query",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas=fuentes,
        latencia_ms=100,
        modelo_llm=None,
    )


def _historial_repo_mock(items: list[ConsultaHistorial]) -> MagicMock:
    repo = MagicMock()
    repo.listar_todas = AsyncMock(return_value=(items, len(items)))
    return repo


def test_metricas_contexto_403_si_no_es_admin(client: TestClient) -> None:
    """Operador juridico no puede acceder a metricas admin."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/metricas/contexto")

    assert response.status_code == 403


def test_metricas_contexto_200_retorna_metricas_agregadas(
    client: TestClient,
) -> None:
    """Admin recibe DTO con promedios e iteraciones individuales."""
    from src.main import app

    items = [
        _historial_mock(
            consulta_id=1,
            usuario_id=1,
            latencia_expansion_ms=40,
            nodos_ascendidos=3,
            breadcrumbs_count=5,
        ),
        _historial_mock(
            consulta_id=2,
            usuario_id=1,
            latencia_expansion_ms=60,
            nodos_ascendidos=5,
            breadcrumbs_count=9,
        ),
    ]

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: _historial_repo_mock(
        items
    )

    response = client.get("/admin/metricas/contexto")

    assert response.status_code == 200
    data = response.json()
    assert data["total_consultas"] == 2
    assert data["expansion_realizada_count"] == 2
    assert data["latencia_expansion_promedio_ms"] == 50.0
    assert data["nodos_ascendidos_promedio"] == 4.0
    assert data["breadcrumbs_count_promedio"] == 7.0
    assert len(data["iteraciones"]) == 2


def test_metricas_contexto_vacio_retorna_ceros(client: TestClient) -> None:
    """Sin consultas -> promedios 0, iteraciones vacias."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: _historial_repo_mock(
        []
    )

    response = client.get("/admin/metricas/contexto")

    assert response.status_code == 200
    data = response.json()
    assert data["total_consultas"] == 0
    assert data["latencia_expansion_promedio_ms"] == 0.0
    assert data["iteraciones"] == []


def test_metricas_contexto_pasaje_parametro_limite(client: TestClient) -> None:
    """Query param limite se pasa al repo."""
    from src.main import app

    repo = _historial_repo_mock([])

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    client.get("/admin/metricas/contexto?limite=50")

    repo.listar_todas.assert_awaited_once()
    call_kwargs = repo.listar_todas.call_args
    assert call_kwargs.kwargs["por_pagina"] == 50


def _audit_repo_mock(registros: list) -> MagicMock:
    repo = MagicMock()
    repo.listar = AsyncMock(return_value=registros)
    return repo


def test_auditoria_devuelve_registros(client: TestClient) -> None:
    """R6: GET /admin/auditoria devuelve registros (solo admin)."""
    from datetime import datetime

    from src.domain.value_objects.registro_auditoria import RegistroAuditoria
    from src.main import app

    reg = RegistroAuditoria(
        accion="publicar_borrador",
        usuario_id=3,
        entidad="borrador",
        entidad_id=777,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: _audit_repo_mock([reg])

    response = client.get("/admin/auditoria")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["accion"] == "publicar_borrador"
    assert item["usuario_id"] == 3
    assert item["entidad"] == "borrador"
    assert item["entidad_id"] == 777
    assert item["created_at"] is not None


def test_auditoria_filtra_por_accion(client: TestClient) -> None:
    """R6: query param accion se pasa al repo."""
    from src.main import app

    repo = _audit_repo_mock([])
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: repo

    client.get("/admin/auditoria?accion=login")

    repo.listar.assert_awaited_once()
    assert repo.listar.call_args.kwargs["accion"] == "login"


def test_auditoria_bloquea_no_admin(client: TestClient) -> None:
    """R6: operador juridico no puede leer el log de auditoria."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/auditoria")

    assert response.status_code == 403


# ===== GET /admin/pipeline/historial (replay Sala de Control) =====


def _repo_historial_mock(items, total):
    repo = MagicMock()
    repo.listar_admin = AsyncMock(return_value=(items, total))
    return repo


def _historial_admin_item(
    *,
    historial_id: int,
    carnet: str = "9000001",
    nombre: str = "Admin",
    tipo_respuesta: str | None = "consulta_simple",
    respuesta: str | None = "Respuesta del LLM",
) -> ConsultaHistorialAdmin:
    return ConsultaHistorialAdmin(
        id=historial_id,
        expediente_id=4,
        usuario_id=26,
        usuario_carnet=carnet,
        usuario_nombre=nombre,
        pregunta="sentencia del proceso",
        respuesta=respuesta,
        tipo_respuesta=tipo_respuesta,
        latencia_ms=200,
        modelo_llm="llama3:8b",
        fuentes_recuperadas={"fragmentos_count": 2, "scores": [0.9]},
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )


def test_pipeline_historial_devuelve_ejecuciones(client: TestClient) -> None:
    from src.main import app

    historial = _historial_admin_item(historial_id=9)
    repo = _repo_historial_mock([historial], 1)
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    response = client.get("/admin/pipeline/historial")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == 9
    assert item["expediente_id"] == 4
    assert item["usuario_id"] == 26
    assert item["usuario_carnet"] == "9000001"
    assert item["usuario_nombre"] == "Admin"
    assert item["pregunta"] == "sentencia del proceso"
    assert item["tipo_respuesta"] == "consulta_simple"
    assert item["latencia_ms"] == 200
    assert item["modelo_llm"] == "llama3:8b"
    assert item["fuentes_recuperadas"]["fragmentos_count"] == 2
    assert item["created_at"] is not None


def test_pipeline_historial_pasa_paginacion(client: TestClient) -> None:
    from src.main import app

    repo = _repo_historial_mock([], 0)
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    client.get("/admin/pipeline/historial?pagina=2&por_pagina=10")

    repo.listar_admin.assert_awaited_once()
    kwargs = repo.listar_admin.call_args.kwargs
    assert kwargs["pagina"] == 2
    assert kwargs["por_pagina"] == 10
    assert kwargs["usuario_id"] is None
    assert kwargs["expediente_id"] is None
    assert kwargs["tipo_respuesta"] is None
    assert kwargs["estado"] is None


def test_pipeline_historial_pasa_filtros_y_estado(client: TestClient) -> None:
    from src.main import app

    repo = _repo_historial_mock([], 0)
    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: repo

    client.get(
        "/admin/pipeline/historial"
        "?usuario_id=26&expediente_id=4&tipo_respuesta=consulta_simple"
        "&estado=en_progreso&fecha_desde=2026-08-01&texto=radicatoria"
    )

    repo.listar_admin.assert_awaited_once()
    kwargs = repo.listar_admin.call_args.kwargs
    assert kwargs["usuario_id"] == 26
    assert kwargs["expediente_id"] == 4
    assert kwargs["tipo_respuesta"] == "consulta_simple"
    assert kwargs["estado"] == "en_progreso"
    assert kwargs["fecha_desde"] is not None
    assert kwargs["texto"] == "radicatoria"


def test_pipeline_historial_bloquea_no_admin(client: TestClient) -> None:
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/pipeline/historial")

    assert response.status_code == 403


# --- Dashboard admin (resumen general) ---


def _dashboard_repo_mock() -> MagicMock:
    from src.application.ports.consulta_historial_repo import (
        DashboardResumen,
        ResumenDia,
        ResumenModelo,
        ResumenTipo,
        ResumenUsuario,
    )

    repo = MagicMock()
    repo.resumen_dashboard = AsyncMock(
        return_value=DashboardResumen(
            total_consultas=3,
            en_progreso=1,
            completadas=1,
            con_error=1,
            por_tipo=[ResumenTipo(tipo_respuesta="consulta_simple", cantidad=2)],
            por_modelo=[
                ResumenModelo(
                    modelo_llm="llama3:8b",
                    cantidad=2,
                    latencia_promedio_ms=18598.0,
                )
            ],
            por_usuario=[
                ResumenUsuario(
                    usuario_id=1,
                    usuario_carnet="9000001",
                    usuario_nombre="Admin",
                    cantidad=3,
                )
            ],
            consultas_por_dia=[ResumenDia(fecha="2026-08-16", cantidad=3)],
        )
    )
    return repo


def test_dashboard_resumen_200_retorna_agregados(client: TestClient) -> None:
    """Admin recibe el resumen de chats y los endpoints activos.

    Los endpoints se derivan de la config cargada (Settings es lru_cache a
    nivel de clase, así que no se puede reconfigurar por monkeypatch): lo que
    se verifica es que el Dashboard informe el endpoint que el pipeline usa.
    """
    from src.config import get_settings
    from src.main import app

    settings = get_settings()
    llm_activo = settings.llm_endpoints[0]

    historial_repo = _dashboard_repo_mock()
    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(
            llm_endpoint_id=llm_activo["id"],
            reranker_endpoint_id=None,
        )
    )

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: historial_repo
    app.dependency_overrides[deps.get_configuracion_rag_repo_dep] = lambda: config_repo

    response = client.get("/admin/dashboard/resumen")

    assert response.status_code == 200
    data = response.json()
    assert data["total_consultas"] == 3
    assert data["en_progreso"] == 1
    assert data["completadas"] == 1
    assert data["con_error"] == 1
    assert data["llm_endpoint"] == {
        "id": llm_activo["id"],
        "provider": llm_activo["provider"],
        "model": llm_activo["model"],
    }
    assert data["embedding_endpoint"]["model"] == settings.embedding_endpoints[0]["model"]
    assert data["por_modelo"][0]["modelo_llm"] == "llama3:8b"
    assert data["por_modelo"][0]["latencia_promedio_ms"] == 18598.0
    assert data["por_usuario"][0]["usuario_carnet"] == "9000001"
    assert data["consultas_por_dia"][0]["fecha"] == "2026-08-16"


def test_dashboard_resumen_no_inventa_reranker_sin_endpoint(client: TestClient) -> None:
    """Con un reranker que no existe en el .env, la card no muestra modelo.

    Es el estado real del pipeline en CPU: sin RERANKER_ENDPOINTS el reranker
    queda deshabilitado y el Dashboard debe decir "No configurado" en vez del
    `bge-reranker-v2-m3` que estaba fijo en el componente.
    """
    from src.main import app

    historial_repo = _dashboard_repo_mock()
    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(
            llm_endpoint_id=None,
            reranker_endpoint_id="reranker_local_inexistente",
        )
    )

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: historial_repo
    app.dependency_overrides[deps.get_configuracion_rag_repo_dep] = lambda: config_repo

    response = client.get("/admin/dashboard/resumen")

    assert response.status_code == 200
    assert response.json()["reranker_endpoint"] is None


def test_dashboard_resumen_403_si_no_es_admin(client: TestClient) -> None:
    """Operador juridico no puede acceder al dashboard."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/dashboard/resumen")

    assert response.status_code == 403


# ===== GET /admin/metricas/salud (HU-22: infraestructura) =====


def _salud_repo_mock(estado) -> MagicMock:
    repo = MagicMock()
    repo.verificar = AsyncMock(return_value=estado)
    return repo


def test_metricas_salud_200_reporta_componentes(client: TestClient) -> None:
    """Admin recibe estado PG/Qdrant + sesiones activas."""
    from src.application.ports.salud_sistema import SaludInfraestructura
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_salud_sistema_repo_dep] = lambda: _salud_repo_mock(
        SaludInfraestructura(postgres_ok=True, qdrant_ok=True, qdrant_puntos=3109)
    )

    response = client.get("/admin/metricas/salud")

    assert response.status_code == 200
    data = response.json()
    assert data["postgres_ok"] is True
    assert data["qdrant_ok"] is True
    assert data["qdrant_puntos"] == 3109
    assert data["sesiones_activas"] == 0


def test_metricas_salud_componente_caido_no_es_500(client: TestClient) -> None:
    """Qdrant caido se reporta con ok=False (200), nunca 500."""
    from src.application.ports.salud_sistema import SaludInfraestructura
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN
    app.dependency_overrides[deps.get_salud_sistema_repo_dep] = lambda: _salud_repo_mock(
        SaludInfraestructura(postgres_ok=True, qdrant_ok=False, qdrant_puntos=0)
    )

    response = client.get("/admin/metricas/salud")

    assert response.status_code == 200
    data = response.json()
    assert data["qdrant_ok"] is False


def test_metricas_salud_403_si_no_es_admin(client: TestClient) -> None:
    """Operador juridico no puede acceder a la salud del sistema."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR

    response = client.get("/admin/metricas/salud")

    assert response.status_code == 403
