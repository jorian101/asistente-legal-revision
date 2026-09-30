"""Tests del use case ObtenerFuentesConsulta (citas RAG por consulta).

Cubre:
- Happy path: fragmentos + scores del JSONB con referencia sanitizada.
- Regla 4 encubierto: entrada ajena/inexistente -> None.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.consultas.obtener_fuentes_historial import ejecutar
from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.entities.expediente import Expediente
from src.domain.entities.norma import Norma
from src.domain.entities.obra import Obra


def _historial(fuentes: dict | None) -> ConsultaHistorial:
    return ConsultaHistorial(
        id=87,
        expediente_id=None,
        usuario_id=26,
        pregunta="test",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas=fuentes,
        latencia_ms=100,
        modelo_llm=None,
    )


def _repo(historial: ConsultaHistorial | None) -> AsyncMock:
    repo = AsyncMock()
    repo.obtener_por_id = AsyncMock(return_value=historial)
    return repo


@pytest.mark.asyncio
async def test_retorna_citas_con_referencia_sanitizada() -> None:
    fuentes = {
        "fragmentos": [
            {
                "id": 5,
                "norma_id": 1,
                "obra_id": None,
                "texto": "Art. 140 CPM...",
                "padre_ref_key": "LOJM_3_MASTER",
                "nivel_jerarquico": 4,
            }
        ],
        "scores": [0.87],
    }

    resultado = await ejecutar(_repo(_historial(fuentes)), historial_id=87, usuario_id=26)

    assert resultado is not None
    assert len(resultado.fragmentos) == 1
    cita = resultado.fragmentos[0]
    assert cita.referencia == "LOJM 3"  # sin sufijo tecnico ni guion bajo
    assert cita.texto == "Art. 140 CPM..."
    assert resultado.scores == (0.87,)
    repo = _repo(None)
    repo.obtener_por_id.assert_not_called()


@pytest.mark.asyncio
async def test_entrada_ajena_devuelve_none_encubierto() -> None:
    resultado = await ejecutar(_repo(None), historial_id=999, usuario_id=26)

    assert resultado is None


@pytest.mark.asyncio
async def test_fuentes_vacias_devuelve_tuplas_vacias() -> None:
    resultado = await ejecutar(
        _repo(_historial({"fragmentos": [], "scores": []})),
        historial_id=87,
        usuario_id=26,
    )

    assert resultado is not None
    assert resultado.fragmentos == ()
    assert resultado.scores == ()


# ----- helpers de repos de enriquecimiento -----
def _norma_repo(normas: dict[int, Norma] | None = None) -> AsyncMock:
    repo = AsyncMock()
    mapping = normas or {}
    repo.get_by_id = AsyncMock(side_effect=lambda nid: mapping.get(nid))
    return repo


def _obra_repo(obras: dict[int, Obra] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.obtener_por_ids = AsyncMock(return_value=obras or {})
    return repo


def _expediente_repo(exps: dict[int, Expediente] | None = None) -> AsyncMock:
    repo = AsyncMock()
    mapping = exps or {}
    repo.obtener = AsyncMock(side_effect=lambda eid: mapping.get(eid))
    return repo


@pytest.mark.asyncio
async def test_obrado_enriquecido_con_tipo_fecha_y_expediente() -> None:
    """Obrado sin padre_ref_key: el enriquecimiento dice qué pieza y de dónde."""
    fuentes = {
        "fragmentos": [
            {
                "id": 10,
                "norma_id": None,
                "obra_id": 5,
                "expediente_id": 2,
                "texto": "VISTOS: ...",
                "padre_ref_key": None,
                "nivel_jerarquico": None,
            }
        ],
        "scores": [0.72],
    }
    obra = Obra(
        id=5,
        expediente_id=2,
        propietario_id=26,
        tipo_documento="auto_vista",
        nombre_archivo="f.pdf",
        contenido_texto="",
        fecha_documento="12/05/2025",
    )
    exp = Expediente(
        id=2,
        numero_caso="3349",
        tipo_proceso="consulta",
        tribunal_origen="TPM",
        procesado_nombre="X",
        delito="d",
        abierto_por=26,
    )

    resultado = await ejecutar(
        _repo(_historial(fuentes)),
        _norma_repo(),
        _obra_repo({5: obra}),
        _expediente_repo({2: exp}),
        historial_id=87,
        usuario_id=26,
    )

    assert resultado is not None
    cita = resultado.fragmentos[0]
    assert cita.referencia is None  # sin padre_ref_key
    assert cita.obra_tipo == "auto_vista"
    assert cita.obra_fecha_documento == "12/05/2025"
    assert cita.expediente_numero == "3349"


@pytest.mark.asyncio
async def test_norma_enriquecida_con_nombre_y_abreviatura() -> None:
    """Norma trae nombre y abreviatura; la referencia legible se conserva."""
    fuentes = {
        "fragmentos": [
            {
                "id": 5,
                "norma_id": 1,
                "obra_id": None,
                "texto": "Art. 140 CPM...",
                "padre_ref_key": "LOJM_3_MASTER",
                "nivel_jerarquico": 4,
            }
        ],
        "scores": [0.87],
    }
    norma = Norma(
        id=1,
        nombre="Ley Organica de la Justicia Militar",
        abreviatura="LOJM",
        tipo="ley_organica",
        jerarquia="militar",
    )

    resultado = await ejecutar(
        _repo(_historial(fuentes)),
        _norma_repo({1: norma}),
        _obra_repo(),
        _expediente_repo(),
        historial_id=87,
        usuario_id=26,
    )

    assert resultado is not None
    cita = resultado.fragmentos[0]
    assert cita.norma_nombre == "Ley Organica de la Justicia Militar"
    assert cita.norma_abreviatura == "LOJM"
    assert cita.referencia == "LOJM 3"


@pytest.mark.asyncio
async def test_sin_repos_sigue_funcionando_backward_compatible() -> None:
    """Sin repos de enriquecimiento, el resultado es como el anterior (campos None)."""
    fuentes = {
        "fragmentos": [
            {
                "id": 10,
                "norma_id": None,
                "obra_id": 5,
                "texto": "VISTOS: ...",
                "padre_ref_key": None,
                "nivel_jerarquico": None,
            }
        ],
        "scores": [0.5],
    }

    resultado = await ejecutar(
        _repo(_historial(fuentes)),
        historial_id=87,
        usuario_id=26,
    )

    assert resultado is not None
    cita = resultado.fragmentos[0]
    assert cita.obra_tipo is None
    assert cita.expediente_numero is None
    assert cita.norma_nombre is None


@pytest.mark.asyncio
async def test_cada_cita_lleva_su_categoria_de_fuente() -> None:
    """norma / jurisprudencia / doctrina / obrado, decidido en el backend."""
    from types import SimpleNamespace

    normas = {
        1: SimpleNamespace(nombre="CPE", abreviatura="CPE", jerarquia="suprema"),
        2: SimpleNamespace(nombre="SCP", abreviatura="SCP-1", jerarquia="jurisprudencia"),
        3: SimpleNamespace(nombre="Libro", abreviatura="LIB-A", jerarquia="doctrina"),
    }
    obras = {
        10: SimpleNamespace(tipo_documento="sentencia", fecha_documento=None, expediente_id=None),
        11: SimpleNamespace(tipo_documento="ejemplo", fecha_documento=None, expediente_id=None),
    }
    norma_repo = AsyncMock()
    norma_repo.get_by_id = AsyncMock(side_effect=lambda i: normas[i])
    obra_repo = AsyncMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value=obras)

    def _f(**k):
        return {"id": 1, "texto": "t", "padre_ref_key": None, "nivel_jerarquico": 4, **k}

    fuentes = {
        "fragmentos": [
            _f(norma_id=1, obra_id=None),
            _f(norma_id=2, obra_id=None),
            _f(norma_id=3, obra_id=None),
            _f(norma_id=None, obra_id=10),
            _f(norma_id=None, obra_id=11),
            _f(norma_id=None, obra_id=None),
        ],
        "scores": [0.1] * 6,
    }

    resultado = await ejecutar(
        _repo(_historial(fuentes)),
        norma_repo,
        obra_repo,
        None,
        historial_id=87,
        usuario_id=26,
    )

    assert resultado is not None
    assert [c.categoria for c in resultado.fragmentos] == [
        "norma",
        "jurisprudencia",
        "doctrina",
        "obrado",
        "jurisprudencia",
        None,
    ]
