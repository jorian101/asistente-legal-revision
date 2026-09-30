"""Contrato del endpoint GET /consultas/historial/{id}/fuentes.

Guarda anti-drift sin BD ni navegador (corre en `make test-cov`):
 - El set de campos publicos de una fuente esta PINNADO (golden). Un rename o
   un campo agregado/quitado en el DTO, en el dataclass del use case o en el
   mapeo del router rompe aca, no en la UI a los golpes.
 - Verifica que un valor enriquecido atraviesa use case + DTO + router hasta el
   JSON (con fakes que devuelven entidades reales; sin Postgres).

Historia: el bug de la etiqueta "LOJM · LOJM 3" y el rename bar_fill/bar-fill
existian porque no habia contrato fijo; esto cierra ese hueco del lado backend.
"""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.consultas.obtener_fuentes_historial import FragmentoCita
from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.entities.expediente import Expediente
from src.domain.entities.norma import Norma
from src.domain.entities.obra import Obra
from src.domain.entities.usuario import Usuario
from src.main import app
from src.routers.consultas import FragmentoCitaDTO

# Contrato publico de una fuente (campos SIEMPRE presentes, aunque sean null).
CAMPOS_FUENTE: set[str] = {
    "id",
    "norma_id",
    "obra_id",
    "texto",
    "referencia",
    "nivel_jerarquico",
    "norma_nombre",
    "norma_abreviatura",
    "obra_tipo",
    "obra_fecha_documento",
    "expediente_numero",
    "categoria",
}

OWNER = Usuario(
    id=26,
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
    yield TestClient(app)
    app.dependency_overrides.clear()


def _historial_con_obrado() -> ConsultaHistorial:
    return ConsultaHistorial(
        id=86,
        expediente_id=None,
        usuario_id=26,
        pregunta="p",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas={
            "fragmentos": [
                {
                    "id": 13,
                    "norma_id": None,
                    "obra_id": 13,
                    "expediente_id": 7,
                    "texto": "VISTOS",
                    "padre_ref_key": None,
                    "nivel_jerarquico": None,
                }
            ],
            "scores": [0.9],
        },
        latencia_ms=10,
        modelo_llm=None,
    )


def test_dto_y_dataclass_respetan_el_contrato() -> None:
    """DTO (HTTP) y dataclass (use case) exponen exactamente los mismos campos."""
    assert set(FragmentoCitaDTO.model_fields) == CAMPOS_FUENTE
    assert {f.name for f in fields(FragmentoCita)} == CAMPOS_FUENTE


def test_endpoint_expone_todos_los_campos(client: TestClient) -> None:
    """Un obrado enriquecido atraviesa la pila y sale con el contrato completo."""
    obra = Obra(
        id=13,
        expediente_id=7,
        propietario_id=26,
        tipo_documento="auto_vista",
        nombre_archivo="x",
        contenido_texto="",
        fecha_documento="2024",
    )
    exp = Expediente(
        id=7,
        numero_caso="3349",
        tipo_proceso="consulta",
        tribunal_origen="TPM",
        procesado_nombre="X",
        delito="d",
        abierto_por=26,
    )
    norma = Norma(
        id=1,
        nombre="Ley Organica",
        abreviatura="LOJM",
        tipo="ley_organica",
        jerarquia="militar",
    )

    hrepo = MagicMock()
    hrepo.obtener_por_id = AsyncMock(return_value=_historial_con_obrado())
    orepo = MagicMock()
    orepo.obtener_por_ids = AsyncMock(return_value={13: obra})
    erepo = MagicMock()
    erepo.obtener = AsyncMock(side_effect=lambda eid: {7: exp}.get(eid))
    nrepo = MagicMock()
    nrepo.get_by_id = AsyncMock(return_value=norma)

    app.dependency_overrides[deps.get_current_user] = lambda: OWNER
    app.dependency_overrides[deps.get_consulta_historial_repo_dep] = lambda: hrepo
    app.dependency_overrides[deps.get_obra_repo_dep] = lambda: orepo
    app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: erepo
    app.dependency_overrides[deps.get_norma_repo] = lambda: nrepo

    r = client.get("/consultas/historial/86/fuentes")
    assert r.status_code == 200
    frag = r.json()["fragmentos"][0]

    # Contrato: todas las claves presentes, ninguna de mas.
    assert set(frag.keys()) == CAMPOS_FUENTE
    # Y el valor real llega al JSON (no se pierde en el mapeo).
    assert frag["obra_tipo"] == "auto_vista"
    assert frag["expediente_numero"] == "3349"
    assert frag["obra_fecha_documento"] == "2024"
