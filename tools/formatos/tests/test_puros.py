"""Tests de las funciones puras de tools/formatos (consenso, alineacion, router).

No requieren docling ni paddle. tools/formatos tiene su propio pyproject sin
pytest, asi que se ejecutan con el entorno del backend (que ya trae pytest y
pymupdf), desde la raiz del repo:

    PYTHONPATH=tools/formatos backend/.venv/bin/python -m pytest tools/formatos/tests -q
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from formatos.consenso import _norm, _tokens, aplicar_consenso
from formatos.estructura_bbox import _normalizar_align, _page_width_pt, recalcular
from formatos.router import classify

# ---------- consenso ----------


def test_norm_quita_acentos_mayusculas_y_puntuacion() -> None:
    assert _norm("  ¡Sentencia N° 12/2026, Vocalía!  ") == "sentencia n 12 2026 vocalia"


def test_tokens_usa_4gramas_y_cae_a_palabras_en_textos_cortos() -> None:
    assert _tokens("uno dos tres cuatro cinco") == {"uno dos tres cuatro", "dos tres cuatro cinco"}
    assert _tokens("uno dos") == {"uno", "dos"}
    assert _tokens("   ") == set()


def _layout(*textos: str, confianza: float | None = None, page: int = 1) -> dict:
    bloques = []
    for t in textos:
        b = {"page": page, "runs": [{"text": t}]}
        if confianza is not None:
            b["confidence"] = confianza
        bloques.append(b)
    return {"blocks": bloques, "meta": {}}


def _paddle(*lineas: str, page: int = 1) -> dict:
    return {
        "engine": "paddle",
        "rss_peak_mb": 100,
        "pages": [{"page": page, "lines": [{"text": t} for t in lineas]}],
    }


def test_consenso_alto_sube_la_confianza_y_no_marca_revision() -> None:
    layout = _layout("Vista la sentencia del tribunal", confianza=0.8)

    revisados = aplicar_consenso(layout, _paddle("Vista la sentencia del tribunal"))

    assert revisados == 0
    assert layout["blocks"][0]["confidence"] == 0.9  # 0.8*0.5 + 1.0*0.5
    assert "review" not in layout["blocks"][0]
    assert layout["meta"]["consenso"] == {
        "motor2": "paddle",
        "rss_peak_mb_motor2": 100,
        "bloques_en_revision": 0,
    }


def test_consenso_bajo_marca_el_bloque_para_revision_humana() -> None:
    layout = _layout("texto que el segundo motor no leyo", confianza=0.8)

    revisados = aplicar_consenso(layout, _paddle("algo totalmente distinto"))

    assert revisados == 1
    assert layout["blocks"][0]["review"] is True
    assert layout["blocks"][0]["confidence"] == 0.4
    assert layout["meta"]["consenso"]["bloques_en_revision"] == 1


def test_consenso_bloque_vacio_queda_en_0_5_y_pagina_sin_referencia_marca_revision() -> None:
    layout = _layout("", "texto en pagina sin ocr", confianza=0.8)
    layout["blocks"][1]["page"] = 7  # el segundo motor solo leyo la pagina 1

    revisados = aplicar_consenso(layout, _paddle("otra cosa"))

    assert layout["blocks"][0]["confidence"] == 0.5
    assert revisados == 1 and layout["blocks"][1]["review"] is True


def test_consenso_confianza_no_supera_0_99() -> None:
    layout = _layout("hola mundo", confianza=1.0)

    aplicar_consenso(layout, _paddle("hola mundo"))

    assert layout["blocks"][0]["confidence"] == 0.99


# ---------- estructura_bbox ----------


def test_ancho_de_pagina_desde_mm_pt_o_default_carta() -> None:
    assert _page_width_pt({"width_mm": 25.4}) == pytest.approx(72.0)
    assert _page_width_pt({"width_pt": 595}) == 595.0
    assert _page_width_pt({}) == 612.0


@pytest.mark.parametrize(
    "center_x,palabras,esperado",
    [
        (306.0, 3, "center"),  # corto y en el centro de una pagina de 612 pt
        (500.0, 3, "right"),  # corto y desplazado a la derecha
        (100.0, 3, "left"),  # corto pero a la izquierda
        (306.0, 30, "justify"),  # parrafo largo
        (306.0, 12, "left"),  # mediano
    ],
)
def test_normalizar_align(center_x: float, palabras: int, esperado: str) -> None:
    assert _normalizar_align(center_x, 612.0, palabras) == esperado


def test_recalcular_usa_bbox_y_cae_a_longitud_sin_bbox() -> None:
    layout = {
        "meta": {"page": {}},
        "blocks": [
            {"runs": [{"text": "TRIBUNAL SUPREMO"}], "bbox": [200, 0, 412, 10]},  # centro 306
            {"runs": [{"text": "titulo corto"}]},  # sin bbox, corto
            {"runs": [{"text": "palabra " * 10}]},  # sin bbox, largo
        ],
    }

    recalcular(layout)

    assert [b["align"] for b in layout["blocks"]] == ["center", "center", "left"]


# ---------- router.classify ----------


def _pdf(ruta: Path, texto: str, **guardar) -> Path:
    doc = pymupdf.Document()
    pagina = doc.new_page()
    if texto:
        pagina.insert_text((72, 72), texto)
    doc.save(ruta, **guardar)
    doc.close()
    return ruta


def test_classify_por_extension_y_contenido(tmp_path: Path) -> None:
    assert classify(tmp_path / "a.docx") == "docx"
    assert classify(tmp_path / "a.txt") == "unsupported"
    assert classify(_pdf(tmp_path / "nativo.pdf", "Texto nativo suficiente. " * 5)) == "native-pdf"
    assert classify(_pdf(tmp_path / "escaneo.pdf", "")) == "scan"


def test_classify_pdf_cifrado_o_corrupto_es_unsupported(tmp_path: Path) -> None:
    cifrado = _pdf(
        tmp_path / "c.pdf", "x", encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="a", user_pw="b"
    )
    corrupto = tmp_path / "roto.pdf"
    corrupto.write_bytes(b"no es un pdf")

    assert classify(cifrado) == "unsupported"
    assert classify(corrupto) == "unsupported"
