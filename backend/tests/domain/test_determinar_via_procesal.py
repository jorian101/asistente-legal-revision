"""Tests DeterminarViaProcesal — regla de oro del modo (P1.1).

Cubre la regla de oro del modo (vault flujo-procesal-consulta, caso 3288):
- Consulta: absolutoria + sin recurso, aunque el oficio diga "apelacion".
- Apelacion incidental: recurso contra auto interlocutorio.
- Apelacion restringida: recurso contra sentencia.
- Rotulo del oficio solo como ultimo recurso.
- Sin datos -> sin_datos_suficientes (no inventar).
"""

from __future__ import annotations

import pytest

from src.domain.services.determinar_via_procesal import (
    RotuloOficio,
    SenalesExpediente,
    SentidoSentencia,
    TipoRecurso,
    ViaProcesal,
    determinar_via_procesal,
)


def test_absolutoria_sin_recurso_es_consulta_aunque_oficio_diga_apelacion() -> None:
    """Regla de oro: el caso 3288 (oficio 'apelacion', procesalmente consulta)."""
    v = determinar_via_procesal(
        SenalesExpediente(
            sentido_sentencia=SentidoSentencia.ABSOLUTORIA,
            tipo_recurso=TipoRecurso.NINGUNO,
            rotulo_oficio=RotuloOficio.APELACION,
        )
    )
    assert v == ViaProcesal.CONSULTA_OFICIO


def test_absolutoria_sin_recurso_rotulo_consulta_es_consulta() -> None:
    """Caso 3349 (golden): oficio consulta + absolutoria sin recurso."""
    v = determinar_via_procesal(
        SenalesExpediente(
            sentido_sentencia=SentidoSentencia.ABSOLUTORIA,
            tipo_recurso=TipoRecurso.NINGUNO,
            rotulo_oficio=RotuloOficio.CONSULTA,
        )
    )
    assert v == ViaProcesal.CONSULTA_OFICIO


def test_recurso_incidental_manda_sobre_oficio() -> None:
    """Caso 3145/3172: recurso incidental manda aunque el oficio no se sepa."""
    v = determinar_via_procesal(
        SenalesExpediente(
            sentido_sentencia=SentidoSentencia.CONDENATORIA,
            tipo_recurso=TipoRecurso.APELACION_INCIDENTAL,
            rotulo_oficio=RotuloOficio.SIN_ROTULO,
        )
    )
    assert v == ViaProcesal.APELACION_INCIDENTAL


def test_recurso_restringido_es_apelacion_restringida() -> None:
    """Recurso contra sentencia -> apelacion restringida."""
    v = determinar_via_procesal(
        SenalesExpediente(
            sentido_sentencia=SentidoSentencia.CONDENATORIA,
            tipo_recurso=TipoRecurso.APELACION_RESTRINGIDA,
            rotulo_oficio=RotuloOficio.APELACION,
        )
    )
    assert v == ViaProcesal.APELACION_RESTRINGIDA


def test_condenatoria_sin_recurso_usa_rotulo() -> None:
    """Sin recurso y sentencia condenatoria: el rotulo decide (ultimo recurso)."""
    v = determinar_via_procesal(
        SenalesExpediente(
            sentido_sentencia=SentidoSentencia.CONDENATORIA,
            tipo_recurso=TipoRecurso.NINGUNO,
            rotulo_oficio=RotuloOficio.CONSULTA,
        )
    )
    assert v == ViaProcesal.CONSULTA_OFICIO


def test_sin_datos_suficientes_no_inventa() -> None:
    """Sin sentido ni recurso ni rotulo -> no inventar via."""
    v = determinar_via_procesal(SenalesExpediente())
    assert v == ViaProcesal.SIN_DATOS


def test_senal_invalida_lanza_valueerror() -> None:
    """Defensa: senal con tipo inesperado -> ValueError (no silencio)."""
    with pytest.raises(ValueError):
        determinar_via_procesal(
            SenalesExpediente(
                sentido_sentencia="absolutoria",  # type: ignore[arg-type]
                tipo_recurso=TipoRecurso.NINGUNO,
                rotulo_oficio=RotuloOficio.SIN_ROTULO,
            )
        )
