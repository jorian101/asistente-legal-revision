"""Tests bloqueantes ExtraerHechosYConcordancias (G3).

Use case pure function: recibe ContextoExpandido -> HechosYConcordancias.
Delega vicios en AnalizadorVicios (G2) y competencia en EvaluadorCompetencia (G5).

RG3: 1 test mínimo por regla/función clave.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.consultas.extraer_hechos import extraer_hechos_y_concordancias
from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects.contexto_expandido import ContextoExpandido, TipoRespuesta
from src.domain.value_objects.hechos_concordancias import HechosYConcordancias
from tests._factories import make_fragmento


class _FakeObra:
    def __init__(
        self,
        tipo_documento: str,
        created_at: date | None = None,
    ) -> None:
        self.tipo_documento = tipo_documento
        self.created_at = created_at


def _ctx(fragmentos: list[Fragmento], tipo: TipoRespuesta = "consulta_simple") -> ContextoExpandido:
    return ContextoExpandido(
        fragmentos_con_padres=tuple(fragmentos),
        scores=tuple(0.9 for _ in fragmentos),
        query_original="test",
        tipo_respuesta=tipo,
        expediente_id=1,
        breadcrumbs=(),
    )


@pytest.mark.asyncio
async def test_contexto_vacio_devuelve_vacio() -> None:
    """Contexto sin fragmentos -> HechosYConcordancias.vacio()."""
    ctx = _ctx([])
    r = await extraer_hechos_y_concordancias(ctx)

    assert r == HechosYConcordancias.vacio()
    assert r.total_fragmentos_analizados == 0


@pytest.mark.asyncio
async def test_delega_vicios_analizador_vicios() -> None:
    """Vicios detectados por AnalizadorVicios se incluyen en resultado."""
    frag = make_fragmento(
        id=1,
        qdrant_point_id="pt-1",
        texto="El procesado no fue notificado de la acusación fiscal, "
        "causándole indefensión procesal.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.vicios.hay_vicios
    assert any(v.tipo == "falta_notificacion" for v in r.vicios.vicios)
    assert any(v.tipo == "indefension" for v in r.vicios.vicios)


@pytest.mark.asyncio
async def test_extrae_hecho_factico_con_foja() -> None:
    """Detecta hecho fáctico y extrae foja referida."""
    frag = make_fragmento(
        id=10,
        qdrant_point_id="pt-10",
        texto="El día 15 de enero de 2024, en la madrugada, el procesado "
        "fue aprehendido en el cuartel. Hecho constatado en foja 12.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.hay_hechos
    hechos_facticos = [h for h in r.hechos if h.tipo_hecho == "hecho_factico"]
    assert len(hechos_facticos) >= 1
    assert hechos_facticos[0].foja_referida == "12"
    assert hechos_facticos[0].fragmento_id == 10


@pytest.mark.asyncio
async def test_extrae_actuacion_procesal() -> None:
    """Detecta actuación procesal (comparecencia, declaración)."""
    frag = make_fragmento(
        id=20,
        qdrant_point_id="pt-20",
        texto="El procesado compareció ante el juez y ratificó su declaración "
        "inicial. La comparecencia se realizó en foja 25.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    actos = [h for h in r.hechos if h.tipo_hecho == "actuacion_procesal"]
    assert len(actos) >= 1
    assert "compareció" in actos[0].texto.lower()
    assert actos[0].foja_referida == "25"


@pytest.mark.asyncio
async def test_extrae_concordancia_cppm() -> None:
    """Detecta cita normativa CPPM y extrae foja."""
    frag = make_fragmento(
        id=30,
        qdrant_point_id="pt-30",
        texto="Conforme al CPPM Art. 361, la notificación defectuosa causa "
        "nulidad. Citado en foja 45 del expediente.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.hay_concordancias
    cppm = [c for c in r.concordancias if c.tipo_norma == "cppm"]
    assert len(cppm) >= 1
    assert "CPPM Art. 361" in cppm[0].norma_citada
    assert cppm[0].foja_referida == "45"


@pytest.mark.asyncio
async def test_extrae_concordancia_cpe() -> None:
    """Detecta cita CPE."""
    frag = make_fragmento(
        id=31,
        qdrant_point_id="pt-31",
        texto="El derecho a la defensa está garantizado por la CPE Art. 115.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    cpe = [c for c in r.concordancias if c.tipo_norma == "cpe"]
    assert len(cpe) >= 1
    assert "CPE Art. 115" in cpe[0].norma_citada


@pytest.mark.asyncio
async def test_extrae_concordancia_ley1970() -> None:
    """Detecta cita Ley 1970."""
    frag = make_fragmento(
        id=32,
        qdrant_point_id="pt-32",
        texto="La competencia de la SAC emana de la Ley 1970 Art. 3.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    l1970 = [c for c in r.concordancias if c.tipo_norma == "ley_1970"]
    assert len(l1970) >= 1
    assert "Ley 1970 Art. 3" in l1970[0].norma_citada


@pytest.mark.asyncio
async def test_extrae_jurisprudencia_tsjm() -> None:
    """Detecta jurisprudencia TSJM."""
    frag = make_fragmento(
        id=33,
        qdrant_point_id="pt-33",
        texto="Conforme a TSJM 2023-045, el plazo fatal es improrrogable.",
    )
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    tsjm = [c for c in r.concordancias if c.tipo_norma == "jurisprudencia_tsjm"]
    assert len(tsjm) >= 1
    assert "TSJM 2023-045" in tsjm[0].norma_citada


@pytest.mark.asyncio
async def test_multiples_fragmentos_acumulan() -> None:
    """Hechos y concordancias de múltiples fragmentos se acumulan."""
    frag1 = make_fragmento(
        id=1,
        qdrant_point_id="pt-1",
        texto="Hecho fáctico: el procesado estaba en el lugar. Foja 10.",
    )
    frag2 = make_fragmento(
        id=2,
        qdrant_point_id="pt-2",
        texto="Norma: CPPM Art. 105 establece plazos. Foja 11.",
    )
    ctx = _ctx([frag1, frag2])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.total_fragmentos_analizados == 2
    assert len(r.hechos) >= 1
    assert len(r.concordancias) >= 1


@pytest.mark.asyncio
async def test_competencia_incluida_con_datos_completos() -> None:
    """Si se pasan datos de expediente, EvaluadorCompetencia se ejecuta."""
    frag = make_fragmento(id=1, qdrant_point_id="pt-1", texto="Texto neutro.")
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(
        ctx,
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal Militar 1",
        expediente_procesado_grado="Capitan",
        expediente_created_at=date(2024, 1, 10),
        obras=[],
        hoy=date(2024, 1, 15),
    )

    assert r.competencia.competencia_global in ("competente", "dudosa")
    assert len(r.competencia.chequeos_competencia) == 3  # materia, territorio, grado
    assert len(r.competencia.chequeos_plazos) == 6  # 6 etapas SAC


@pytest.mark.asyncio
async def test_competencia_vacia_sin_datos_minimos() -> None:
    """Sin datos mínimos de expediente -> competencia vacía (no rompe)."""
    frag = make_fragmento(id=1, qdrant_point_id="pt-1", texto="Texto.")
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.competencia == HechosYConcordancias.vacio().competencia


@pytest.mark.asyncio
async def test_fragmento_corto_no_genera_hecho() -> None:
    """Fragmento < 30 chars no produce hechos (ruido)."""
    frag = make_fragmento(id=1, qdrant_point_id="pt-1", texto="Art.")
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    assert r.hechos == ()


@pytest.mark.asyncio
async def test_fragmento_largo_trunca_hecho_a_300() -> None:
    """Hecho extraído se trunca a máx 300 chars."""
    texto_largo = "Hecho fáctico muy largo: " + "x" * 400
    frag = make_fragmento(id=1, qdrant_point_id="pt-1", texto=texto_largo)
    ctx = _ctx([frag])

    r = await extraer_hechos_y_concordancias(ctx)

    if r.hechos:
        assert len(r.hechos[0].texto) <= 300


@pytest.mark.asyncio
async def test_hechos_y_concordancias_vacio_factory() -> None:
    """HechosYConcordancias.vacio() devuelve instancia válida."""
    v = HechosYConcordancias.vacio()
    assert v.hechos == ()
    assert v.concordancias == ()
    assert v.vicios.total == 0
    assert v.competencia.competencia_global == "competente"
    assert v.total_fragmentos_analizados == 0


@pytest.mark.asyncio
async def test_determinismo_mismo_input_mismo_output() -> None:
    """Determinismo: mismo contexto -> mismo resultado."""
    frag = make_fragmento(
        id=42,
        qdrant_point_id="pt-42",
        texto="El procesado compareció en foja 5. CPPM Art. 105 cita plazos.",
    )
    ctx = _ctx([frag])

    r1 = await extraer_hechos_y_concordancias(ctx)
    r2 = await extraer_hechos_y_concordancias(ctx)

    assert r1.hechos == r2.hechos
    assert r1.concordancias == r2.concordancias
    assert r1.vicios.vicios == r2.vicios.vicios


# --- BUGFIX F1: nombres cruzados CPPM/CPM en regex de normas ---


@pytest.mark.asyncio
async def test_codigo_penal_militar_es_cpm_no_cppm() -> None:
    """'Código Penal Militar Art. X' -> tipo_norma='cpm' (no cppm).

    Bugfix: la regex vieja de CPPM matcheaba "Código Penal Militar",
    atribuyendo al CPM las citas del Código Penal Militar."""
    frag = make_fragmento(
        id=40,
        qdrant_point_id="pt-40",
        texto="La conducta se tipifica en el Código Penal Militar Art. 140.",
    )
    r = await extraer_hechos_y_concordancias(_ctx([frag]))

    cpm = [c for c in r.concordancias if c.tipo_norma == "cpm"]
    cppm = [c for c in r.concordancias if c.tipo_norma == "cppm"]
    assert len(cpm) >= 1
    assert "Art. 140" in cpm[0].norma_citada
    assert cppm == []


@pytest.mark.asyncio
async def test_codigo_procesal_penal_militar_es_cppm() -> None:
    """'Código Procesal Penal Militar Art. X' -> tipo_norma='cppm'.

    Bugfix: la regex vieja de CPM matcheaba "Código Procesal Militar"
    (inexistente) y el nombre real del CPPM nunca matcheaba."""
    frag = make_fragmento(
        id=41,
        qdrant_point_id="pt-41",
        texto="Se remite en consulta conforme al Código Procesal Penal Militar Art. 194.",
    )
    r = await extraer_hechos_y_concordancias(_ctx([frag]))

    cppm = [c for c in r.concordancias if c.tipo_norma == "cppm"]
    cpm = [c for c in r.concordancias if c.tipo_norma == "cpm"]
    assert len(cppm) >= 1
    assert "Art. 194" in cppm[0].norma_citada
    assert cpm == []


@pytest.mark.asyncio
async def test_codigo_de_procedimiento_penal_militar_es_cppm() -> None:
    """Variante formal del título: 'Código de Procedimiento Penal Militar'."""
    frag = make_fragmento(
        id=42,
        qdrant_point_id="pt-42",
        texto="Conforme al Código de Procedimiento Penal Militar Art. 201 se formula el proyecto.",
    )
    r = await extraer_hechos_y_concordancias(_ctx([frag]))

    cppm = [c for c in r.concordancias if c.tipo_norma == "cppm"]
    assert len(cppm) >= 1


@pytest.mark.asyncio
async def test_abreviaturas_cppm_y_cpm_sigue_funcionando() -> None:
    """Las abreviaturas CPPM/CPM siguen clasificando igual tras el fix."""
    frag_a = make_fragmento(
        id=43, qdrant_point_id="pt-43", texto="CPPM Art. 361 exige notificación."
    )
    frag_b = make_fragmento(
        id=44, qdrant_point_id="pt-44", texto="El CPM Art. 107 tipifica la violación de normas."
    )
    r = await extraer_hechos_y_concordancias(_ctx([frag_a, frag_b]))

    assert any(c.tipo_norma == "cppm" for c in r.concordancias)
    assert any(c.tipo_norma == "cpm" for c in r.concordancias)
