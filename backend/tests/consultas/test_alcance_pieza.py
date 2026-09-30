"""Alcance por la pieza procesal que nombra la consulta (ADR-005, seccion B).

Los ejemplos salen de las definiciones del ADR-005 (quien genera cada pieza y que contiene), no
de las preguntas del golden de evaluacion.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from src.domain.services.pieza_procesal import es_pregunta_amplia, tipos_nombrados

DICTAMENES = {"dictamen_radicatoria", "dictamen_fondo"}


@pytest.mark.parametrize(
    ("consulta", "tipos"),
    [
        ("¿Cuál es el sentido del fallo?", {"sentencia"}),
        ("¿Qué declara la resolución recurrida?", {"auto_interlocutorio"}),
        ("¿Qué agravios expresa el recurrente?", {"memorial_apelacion"}),
        ("¿Cuándo se firmó el oficio de elevación?", {"oficio_elevacion"}),
        ("¿Qué consta en el acta del juicio oral?", {"acta_audiencia"}),
        ("¿Qué pide el requerimiento?", {"requerimiento_fiscal"}),
        ("Resumí lo que dictaminó el auditor", DICTAMENES),
        ("¿Qué dice la relación de obrados?", {"relacion_obrados"}),
        # Dos piezas nombradas: el alcance son las dos.
        ("¿El fiscal comparte los agravios?", {"requerimiento_fiscal", "memorial_apelacion"}),
    ],
)
def test_tipos_nombrados_segun_el_adr_005(consulta, tipos):
    assert tipos_nombrados(consulta) == tipos


@pytest.mark.parametrize(
    "consulta",
    [
        "¿De qué trata el expediente?",
        "¿Llegó en apelación o en consulta?",  # la via procesal no es una pieza
        "¿Quién es el procesado?",
    ],
)
def test_sin_pieza_nombrada_no_hay_alcance(consulta):
    assert tipos_nombrados(consulta) == frozenset()


OBRAS = [
    SimpleNamespace(id=1, tipo_documento="sentencia", corpus_ref=None),
    SimpleNamespace(id=2, tipo_documento="dictamen_fondo", corpus_ref=None),
    SimpleNamespace(id=3, tipo_documento="dictamen_radicatoria", corpus_ref=None),
    SimpleNamespace(id=4, tipo_documento="otro", corpus_ref=None),
    SimpleNamespace(id=5, tipo_documento="dictamen_fondo", corpus_ref="SCP-1"),  # puntero
]


def _pipeline(obras=OBRAS) -> PipelineRAG:
    obra_repo = MagicMock()
    obra_repo.listar_por_expediente = AsyncMock(return_value=obras)
    obra_repo.obtener_por_ids = AsyncMock(return_value={})
    buscador = MagicMock(spec=HybridSearcher)
    buscador.buscar = AsyncMock(return_value=[])
    return PipelineRAG(
        buscador=buscador, reranker_svc=MagicMock(), config_repo=MagicMock(), obra_repo=obra_repo
    )


async def _entender(pipeline, consulta, expediente_id=7, obra_ids=None):
    return await pipeline._fase_entender(
        MagicMock(),
        consulta=consulta,
        usuario_id=5,
        expediente_id=expediente_id,
        tipo_proceso=None,
        tipo_forzado=None,
        obra_ids=obra_ids,
        corpus_refs=None,
    )


@pytest.mark.asyncio
async def test_consulta_simple_que_nombra_la_pieza_acota_a_sus_obras():
    tipo, filtros, _ = await _entender(_pipeline(), "¿Qué dictaminó el auditor?")
    assert tipo == "consulta_simple"
    assert sorted(filtros["obra_ids"]) == [2, 3]  # sin la obra puntero


@pytest.mark.asyncio
async def test_sin_pieza_o_sin_obras_de_ese_tipo_el_alcance_es_el_expediente():
    _, filtros, _ = await _entender(_pipeline(), "¿De qué trata el expediente?")
    assert "obra_ids" not in filtros
    _, filtros, _ = await _entender(_pipeline(obras=OBRAS[3:4]), "¿Qué dictaminó el auditor?")
    assert "obra_ids" not in filtros


@pytest.mark.asyncio
async def test_la_seleccion_del_usuario_manda():
    pipeline = _pipeline()
    pipeline._obra_repo.obtener_por_ids = AsyncMock(
        return_value={1: SimpleNamespace(corpus_ref=None, expediente_id=7)}
    )
    _, filtros, _ = await _entender(pipeline, "¿Qué dictaminó el auditor?", obra_ids=[1])
    assert filtros["obra_ids"] == [1]


@pytest.mark.asyncio
async def test_los_borradores_no_se_acotan():
    tipo, filtros, _ = await _entender(_pipeline(), "redactar auto de vista de la consulta")
    assert tipo != "consulta_simple"
    assert "obra_ids" not in filtros


@pytest.mark.asyncio
async def test_completar_obras_recibe_el_alcance_de_la_pieza():
    pipeline = _pipeline()
    pipeline._completar_obras_del_expediente = AsyncMock()
    cfg = SimpleNamespace(top_k_denso=10, top_k_lexico=5)
    await pipeline._fase_buscar(
        MagicMock(),
        consulta="¿Qué dictaminó el auditor?",
        usuario_id=5,
        expediente_id=7,
        obra_ids=None,
        tipo_respuesta="consulta_simple",
        filtros={"expediente_id": "7", "obra_ids": [2, 3]},
        refs_punteros=[],
        cfg=cfg,
    )
    assert pipeline._completar_obras_del_expediente.await_args.args[3] == [2, 3]


# Politica de preguntas amplias, criterio 1: ejemplos de la propia politica, no del golden.
@pytest.mark.parametrize(
    "consulta",
    [
        "¿De qué trata el caso?",
        "Haceme un resumen del expediente",
        "Resumí el caso",
        "¿Cuáles son los hechos?",
        "¿Cuál es la situación jurídica del procesado?",
        "¿Quién es el procesado?",
        "¿Cuál es la imputación?",
    ],
)
def test_pregunta_amplia(consulta):
    assert es_pregunta_amplia(consulta)


@pytest.mark.parametrize(
    "consulta",
    [
        "¿Cuál es el número de la sentencia?",  # dato puntual
        "¿Qué hechos da por probados la sentencia?",  # nombra una pieza: manda el alcance por pieza
        "¿Cuál es el plazo para apelar?",
    ],
)
def test_no_es_pregunta_amplia(consulta):
    assert not es_pregunta_amplia(consulta)
