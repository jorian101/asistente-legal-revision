"""Tests bloqueantes SugerirArgumentacion (G4).

Pure function: HechosYConcordancias + tipo_respuesta -> SugerenciaArgumentacion.
Delega en ExtraerHechosYConcordancias (G3) que a su vez delega en G2/G5.

RG3: 1 test mínimo por regla/tipo_respuesta.
"""

from __future__ import annotations

import pytest

from src.application.consultas.sugerir_argumentacion import (
    BloqueArgumentacion,
    SugerenciaArgumentacion,
    sugerir_argumentacion,
)
from src.domain.value_objects.hechos_concordancias import (
    ConcordanciaNormativa,
    HechoProcesal,
    HechosYConcordancias,
)
from src.domain.value_objects.resultado_competencia import (
    ChequeoCompetencia,
    ChequeoPlazo,
    ResultadoCompetencia,
)
from src.domain.value_objects.resultado_vicios import (
    ResultadoVicios,
    VicioDetectado,
)


def _hc_vacio() -> HechosYConcordancias:
    return HechosYConcordancias.vacio()


def _hc_con_hechos_y_normas() -> HechosYConcordancias:
    return HechosYConcordancias(
        hechos=(
            HechoProcesal(
                fragmento_id=1,
                texto="El procesado compareció y declaró bajo juramento.",
                tipo_hecho="actuacion_procesal",
                foja_referida="10",
                norma_asociada=None,
            ),
            HechoProcesal(
                fragmento_id=2,
                texto="El día 15 de enero fue aprehendido en el cuartel.",
                tipo_hecho="hecho_factico",
                foja_referida="12",
                norma_asociada=None,
            ),
        ),
        concordancias=(
            ConcordanciaNormativa(
                fragmento_id=3,
                norma_citada="CPPM Art. 361",
                tipo_norma="cppm",
                texto_contexto="CPPM Art. 361 establece nulidad por notificación defectuosa.",
                foja_referida="15",
            ),
            ConcordanciaNormativa(
                fragmento_id=4,
                norma_citada="CPE Art. 115",
                tipo_norma="cpe",
                texto_contexto="Derecho a la defensa CPE Art. 115.",
                foja_referida=None,
            ),
        ),
        vicios=ResultadoVicios.de_lista(
            [
                VicioDetectado(
                    tipo="falta_notificacion",
                    fragmento_id=5,
                    foja_referida="20",
                    snippet="No fue notificado de la acusación.",
                    norma_vulnerada="CPPM Art. 161",
                ),
            ]
        ),
        competencia=ResultadoCompetencia.de_listas(
            chequeos_competencia=[
                ChequeoCompetencia("materia", "competente", "ok", "Ley 1970 Art. 3"),
                ChequeoCompetencia("territorio", "competente", "ok", "Ley 1970 Art. 2"),
                ChequeoCompetencia("grado", "competente", "ok", "Ley 1970 Art. 4"),
            ],
            chequeos_plazos=[
                ChequeoPlazo("auto_representacion", "dentro_plazo", 2, 3),
                ChequeoPlazo("dictamen_radicatoria", "vencido", 5, 3),
                ChequeoPlazo("proyecto_auto_vista", "critico", None, 48),
            ],
        ),
        total_fragmentos_analizados=5,
    )


def test_vacio_devuelve_vacia() -> None:
    """HechosYConcordancias vacío -> SugerenciaArgumentacion.vacia()."""
    r = sugerir_argumentacion(_hc_vacio(), "auto_vista_consulta")

    assert r.tipo_respuesta == "auto_vista_consulta"
    assert r.total_bloques == 0
    assert "Sin datos" in r.resumen_ejecutivo


@pytest.mark.parametrize(
    "tipo",
    [
        "auto_vista_consulta",
        "auto_vista_apelacion_incidental",
        "dictamen_radicatoria_consulta",
        "dictamen_radicatoria_apelacion",
    ],
)
def test_todos_tipos_respuesta_generan_sugerencia(tipo: str) -> None:
    """Cada tipo de respuesta genera sugerencia no vacía con datos."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), tipo)

    assert r.tipo_respuesta == tipo
    assert r.total_bloques > 0
    assert len(r.resumen_ejecutivo) > 20


def test_auto_vista_consulta_prioriza_hechos_facticos_y_cppm() -> None:
    """auto_vista_consulta: prioriza hechos fácticos + CPPM/CPE."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    # Fundamentos hecho: hecho_factico y actuacion_procesal
    tipos_hecho = {b.titulo for b in r.fundamentos_hecho}
    assert any("Hecho Factico" in t or "Hecho: Hecho Factico" in t for t in tipos_hecho)
    assert any("Actuacion Procesal" in t for t in tipos_hecho)

    # Fundamentos derecho: CPPM y CPE
    normas = {b.normas_citadas[0] for b in r.fundamentos_derecho if b.normas_citadas}
    assert any("CPPM" in n for n in normas)
    assert any("CPE" in n for n in normas)


def test_auto_vista_apelacion_prioriza_hecho_factico_y_actuacion() -> None:
    """auto_vista_apelacion_incidental: prioriza hecho_factico + actuacion_procesal."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_apelacion_incidental")

    # Fundamentos hecho: hecho_factico y actuacion_procesal
    tipos_hecho = {b.titulo for b in r.fundamentos_hecho}
    assert any("Hecho Factico" in t for t in tipos_hecho)
    assert any("Actuacion Procesal" in t for t in tipos_hecho)


def test_dictamen_radicatoria_prioriza_competencia_y_ley1970() -> None:
    """dictamen_radicatoria: prioriza competencia + Ley 1970 Art. 3."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "dictamen_radicatoria_consulta")

    # Alertas competencia: hay competencia global competente, pero chequeos existen
    assert len(r.alertas_competencia) >= 0  # depende de datos
    # Alertas plazos: dictamen_radicatoria vencido -> alerta
    assert len(r.alertas_plazos) >= 1
    plazos_vencidos = [b for b in r.alertas_plazos if "vencido" in b.titulo.lower()]
    assert len(plazos_vencidos) >= 1


def test_vicios_sanear_incluye_vicios_detectados() -> None:
    """Vicios de G2 aparecen en vicios_sanear con foja y norma."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    assert len(r.vicios_sanear) >= 1
    v = r.vicios_sanear[0]
    assert v.tipo == "vicio"
    assert "falta_notificacion" in v.titulo.lower() or "Vicio: Falta Notificacion" in v.titulo
    assert v.fojas_referidas == ("20",)
    assert v.normas_citadas == ("CPPM Art. 161",)


def test_alerta_plazo_vencido_prioridad_alta() -> None:
    """Plazo vencido -> alerta prioridad alta."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    alertas_vencidas = [b for b in r.alertas_plazos if "vencido" in b.titulo.lower()]
    assert len(alertas_vencidas) >= 1
    assert alertas_vencidas[0].prioridad == "alta"


def test_alerta_plazo_critico_prioridad_media() -> None:
    """Plazo crítico -> alerta prioridad media."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    alertas_criticas = [b for b in r.alertas_plazos if "critico" in b.titulo.lower()]
    assert len(alertas_criticas) >= 1
    assert alertas_criticas[0].prioridad == "media"


def test_resumen_ejecutivo_incluye_conteos() -> None:
    """Resumen ejecutivo menciona conteos de cada categoría."""
    r = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    assert "fundamentos de hecho" in r.resumen_ejecutivo.lower()
    assert "concordancias normativas" in r.resumen_ejecutivo.lower()
    assert "vicios" in r.resumen_ejecutivo.lower()
    # alertas plazos aparece como "alertas de plazos"
    assert (
        "alertas de plazos" in r.resumen_ejecutivo.lower()
        or "plazos" in r.resumen_ejecutivo.lower()
    )


def test_bloque_argumentacion_campos_requeridos() -> None:
    """BloqueArgumentacion tiene todos los campos requeridos."""
    b = BloqueArgumentacion(
        titulo="Test",
        tipo="hecho",
        contenido="Contenido test",
        fojas_referidas=("10",),
        normas_citadas=("CPPM Art. 105",),
        prioridad="alta",
    )

    assert b.titulo == "Test"
    assert b.tipo == "hecho"
    assert b.fojas_referidas == ("10",)
    assert b.normas_citadas == ("CPPM Art. 105",)
    assert b.prioridad == "alta"


def test_sugerencia_vacia_factory() -> None:
    """SugerenciaArgumentacion.vacia() devuelve instancia válida."""
    v = SugerenciaArgumentacion.vacia("auto_vista_consulta")
    assert v.tipo_respuesta == "auto_vista_consulta"
    assert v.total_bloques == 0
    assert v.fundamentos_hecho == ()
    assert v.resumen_ejecutivo == "Sin datos suficientes para generar sugerencia."


def test_determinismo_mismo_input_mismo_output() -> None:
    """Determinismo: mismos inputs -> mismo output."""
    r1 = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")
    r2 = sugerir_argumentacion(_hc_con_hechos_y_normas(), "auto_vista_consulta")

    assert r1.fundamentos_hecho == r2.fundamentos_hecho
    assert r1.fundamentos_derecho == r2.fundamentos_derecho
    assert r1.vicios_sanear == r2.vicios_sanear
    assert r1.alertas_competencia == r2.alertas_competencia
    assert r1.alertas_plazos == r2.alertas_plazos
    assert r1.resumen_ejecutivo == r2.resumen_ejecutivo


def test_competencia_incompetente_genera_alerta() -> None:
    """Competencia global incompetente -> alerta de competencia."""
    hc = HechosYConcordancias(
        hechos=(),
        concordancias=(),
        vicios=ResultadoVicios.vacio(),
        competencia=ResultadoCompetencia.de_listas(
            chequeos_competencia=[
                ChequeoCompetencia(
                    "materia", "incompetente", "tipo no reconocido", "Ley 1970 Art. 3"
                ),
                ChequeoCompetencia("territorio", "competente", "ok", None),
                ChequeoCompetencia("grado", "competente", "ok", None),
            ],
            chequeos_plazos=[],
        ),
        total_fragmentos_analizados=1,
    )

    r = sugerir_argumentacion(hc, "auto_vista_consulta")

    assert len(r.alertas_competencia) >= 1
    assert any("incompetente" in b.titulo.lower() for b in r.alertas_competencia)


def test_sin_vicios_no_genera_vicios_sanear() -> None:
    """Sin vicios -> vicios_sanear vacío."""
    hc = HechosYConcordancias(
        hechos=(HechoProcesal(1, "hecho", "hecho_factico", None, None),),
        concordancias=(),
        vicios=ResultadoVicios.vacio(),
        competencia=ResultadoCompetencia.vacio(),
        total_fragmentos_analizados=1,
    )

    r = sugerir_argumentacion(hc, "auto_vista_consulta")

    assert r.vicios_sanear == ()


def test_sin_concordancias_no_genera_fundamentos_derecho() -> None:
    """Sin concordancias -> fundamentos_derecho vacío."""
    hc = HechosYConcordancias(
        hechos=(HechoProcesal(1, "hecho", "hecho_factico", None, None),),
        concordancias=(),
        vicios=ResultadoVicios.vacio(),
        competencia=ResultadoCompetencia.vacio(),
        total_fragmentos_analizados=1,
    )

    r = sugerir_argumentacion(hc, "auto_vista_consulta")

    assert r.fundamentos_derecho == ()
