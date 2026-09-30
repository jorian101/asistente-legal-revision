"""Tests del validador de dominio de ConfiguracionRAG (HU-23)."""

from __future__ import annotations

import pytest

from src.domain.entities.configuracion_rag import validar_parametros_ajustables


def test_acepta_valores_validos_y_normaliza() -> None:
    limpios = validar_parametros_ajustables(
        {"score_threshold": 0.6, "top_k_final": 10, "temperatura": 0.2}
    )

    assert limpios == {"score_threshold": 0.6, "top_k_final": 10, "temperatura": 0.2}


def test_limites_de_rango_son_inclusivos() -> None:
    limpios = validar_parametros_ajustables({"score_threshold": 1.0, "max_profundidad_bfs": 1})

    assert limpios == {"score_threshold": 1.0, "max_profundidad_bfs": 1}


def test_rechaza_clave_desconocida() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        validar_parametros_ajustables({"modelo_embeddings": "bge-m3"})


def test_rechaza_bool_como_valor() -> None:
    # bool es subclase de int: debe rechazarse explicitamente.
    with pytest.raises(ValueError, match="numérico"):
        validar_parametros_ajustables({"top_k_final": True})


def test_rechaza_string_como_valor() -> None:
    with pytest.raises(ValueError, match="numérico"):
        validar_parametros_ajustables({"top_k_denso": "40"})


def test_rechaza_fuera_de_rango_mencionando_campo() -> None:
    with pytest.raises(ValueError, match="top_k_denso"):
        validar_parametros_ajustables({"top_k_denso": 500})

    with pytest.raises(ValueError, match="temperatura"):
        validar_parametros_ajustables({"temperatura": -0.5})
