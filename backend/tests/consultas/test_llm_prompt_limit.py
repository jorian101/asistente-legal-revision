"""Tests F2 — presupuesto de tokens del contexto inyectado al prompt LLM.

Antes (P5.5) el recorte era por cantidad de fragmentos; desde F1/F2 el
ConstructorMensajes presupuesta por tokens aproximados con bloques enteros.
"""

from __future__ import annotations

import logging

from src.application.services.constructor_mensajes import RESERVA_SALIDA, ConstructorMensajes
from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects.contexto_expandido import ContextoExpandido


def _frag(i: int) -> Fragmento:
    return Fragmento(
        id=i,
        norma_id=1,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=f"q{i}",
        texto=f"Fragmento numero {i}",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


def _contexto(n: int) -> ContextoExpandido:
    return ContextoExpandido(
        fragmentos_con_padres=tuple(_frag(i) for i in range(n)),
        scores=tuple(1.0 for _ in range(n)),
        query_original="q",
        tipo_respuesta="auto_vista_consulta",
        expediente_id=None,
        breadcrumbs=tuple((f"q{i}",) for i in range(n)),
    )


def test_presupuesto_pequeno_recorta() -> None:
    """Con presupuesto chico y 10 fragmentos, solo los primeros entran."""
    ctor = ConstructorMensajes(presupuesto_tokens=30)
    mensajes = ctor.construir("PREFIJO {{contexto_expandido}} SUFIJO", _contexto(10))
    assert "Fragmento numero 0" in mensajes.user
    assert "Fragmento numero 9" not in mensajes.user
    assert "{{contexto_expandido}}" not in mensajes.user


def test_presupuesto_suficiente_incluye_todos() -> None:
    ctor = ConstructorMensajes()
    mensajes = ctor.construir("{{contexto_expandido}}", _contexto(10))
    assert "Fragmento numero 9" in mensajes.user


def test_al_menos_un_bloque_siempre_entra() -> None:
    """Un fragmento mas grande que el presupuesto igual entra (nunca vacio por recorte)."""
    ctor = ConstructorMensajes(presupuesto_tokens=1)
    mensajes = ctor.construir("{{contexto_expandido}}", _contexto(1))
    assert "Fragmento numero 0" in mensajes.user


def test_ventana_presupuesta_contra_plantilla_y_reserva() -> None:
    """A.1: presupuesto = ventana − plantilla − RESERVA_SALIDA, con el tope global."""
    ctor = ConstructorMensajes(ventana_tokens=RESERVA_SALIDA + 1000)
    # plantilla de 3.600 chars = 900 tokens -> quedan 100 tokens (400 chars) de contexto
    assert ctor._presupuesto_contexto("x" * 3600 + "{{contexto_expandido}}") == 100
    # ventana enorme: manda el tope global (LLM_PRESUPUESTO_TOKENS)
    assert ConstructorMensajes(ventana_tokens=131072)._presupuesto_contexto("x") == 4096
    # sin ventana: comportamiento anterior, presupuesto fijo
    assert ConstructorMensajes(presupuesto_tokens=30)._presupuesto_contexto("x" * 10**6) == 30


def test_ventana_chica_recorta_contexto_y_avisa_desborde(caplog) -> None:
    """La plantilla no se recorta: queda >= 1 bloque y el desborde se loguea."""
    ctor = ConstructorMensajes(ventana_tokens=RESERVA_SALIDA + 100)
    with caplog.at_level(logging.WARNING):
        mensajes = ctor.construir("x" * 2000 + "{{contexto_expandido}}", _contexto(10))
    assert "Fragmento numero 0" in mensajes.user
    assert "Fragmento numero 9" not in mensajes.user
    assert "excede la ventana" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        ConstructorMensajes(ventana_tokens=8192).construir("{{contexto_expandido}}", _contexto(2))
    assert "excede la ventana" not in caplog.text
