"""Reglas globales de redacción de borradores (criterio del vocal / auditor)."""

from __future__ import annotations

from src.application.borradores.generar_borrador import con_reglas_de_redaccion


def test_borrador_lleva_las_reglas_antes_de_la_plantilla():
    prompt = con_reglas_de_redaccion("PLANTILLA", "auto_vista_apelacion_incidental")

    assert prompt.endswith("PLANTILLA")
    assert "únicamente el texto del documento" in prompt
    assert "no completes fojas" in prompt.lower()
    assert "pendiente" in prompt


def test_consulta_simple_no_recibe_reglas_de_documento():
    assert con_reglas_de_redaccion("PLANTILLA", "consulta_simple") == "PLANTILLA"


def test_regla_de_citado_admite_segmentos_criterio_y_plantilla():
    """Toda cita debe estar en lo que el modelo recibió: segmentos [S#], criterio o plantilla."""
    prompt = con_reglas_de_redaccion("PLANTILLA", "auto_vista_consulta").lower()

    assert "segmentos numerados [s#]" in prompt
    assert "criterio del vocal" in prompt
    assert "plantilla" in prompt
    assert "de memoria" in prompt
    assert "no escribas los rótulos [s#]" in prompt
