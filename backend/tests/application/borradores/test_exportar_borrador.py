"""Tests de ExportarBorrador — conversion markdown -> .docx.

Verifica que el UC produce bytes de un docx valido (ZIP: PK\x03\x04)
y que el contenido markdown se refleja en el documento.
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from src.application.borradores.exportar_borrador import (
    exportar_borrador_docx,
    normalizar_fuente,
)
from src.domain.entities.borrador import Borrador


def _borrador(contenido: str) -> Borrador:
    return Borrador(
        id=7,
        expediente_id=1,
        propietario_id=2,
        tipo="proyecto_auto_vista_consulta",
        contenido=contenido,
    )


def test_exporta_docx_valido() -> None:
    """Los bytes devueltos son un .docx valido (ZIP magic)."""
    contenido = "# AUTO DE VISTA\n\nTexto del auto."
    b = _borrador(contenido)

    docx = exportar_borrador_docx(b)

    assert isinstance(docx, bytes)
    assert docx.startswith(b"PK\x03\x04"), "docx es un ZIP (PK magic)"


def test_exporta_incluye_titulo_y_contenido() -> None:
    """El docx generado contiene los parrafos del borrador."""
    b = _borrador("# AUTO DE VISTA\n\nFundamento primero.\n## CONSIDERANDO\n\nTexto.")

    docx = exportar_borrador_docx(b)
    doc = Document(io.BytesIO(docx))

    textos = [p.text for p in doc.paragraphs]
    assert any("AUTO DE VISTA" in t for t in textos)
    assert any("Fundamento primero." in t for t in textos)
    assert any("CONSIDERANDO" in t for t in textos)


def test_exporta_contenido_vacio_no_rompe() -> None:
    """Borrador sin contenido genera docx valido (no raise)."""
    b = _borrador("")

    docx = exportar_borrador_docx(b)

    assert docx.startswith(b"PK\x03\x04")


def test_exporta_layout_fiel_respeta_estilo() -> None:
    """Si layout existe, el docx usa su align/bold/size/font."""
    b = _borrador("# AUTO DE VISTA\nTexto viejo")
    b.layout = [
        {
            "texto": "AUTO DE VISTA",
            "align": "center",
            "bold": True,
            "underline": False,
            "size_pt": 14,
            "font": "Times New Roman",
            "heading": 1,
        },
        {
            "texto": "Fundamento editado",
            "align": "justify",
            "bold": False,
            "underline": False,
            "size_pt": None,
            "font": None,
            "heading": 0,
        },
    ]
    docx = exportar_borrador_docx(b)
    doc = Document(io.BytesIO(docx))
    textos = [p.text for p in doc.paragraphs]
    assert "AUTO DE VISTA" in textos[0]
    assert "Fundamento editado" in textos[1]
    # El segundo layout no debe contener el viejo "Texto viejo"
    assert "Texto viejo" not in " ".join(textos)


def test_resolver_contexto_export_defaults() -> None:
    """resolver_contexto_export sin formato devuelve defaults carta/Legal/Arial12."""
    from src.application.borradores.exportar_borrador import resolver_contexto_export

    ctx = resolver_contexto_export(None)
    assert ctx["tamano_hoja"] == "carta"
    assert ctx["margenes"]["left"] == 40
    assert ctx["font"] == "Arial"
    assert ctx["size_pt"] == 12


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("ArialMT", "Arial"),
        ("Arial-BoldMT", "Arial"),
        ("ABCDEF+Arial", "Arial"),
        ("TimesNewRomanPSMT", "Times New Roman"),
        ("Arial", "Arial"),
        (None, None),
    ],
)
def test_normalizar_fuente(entrada, esperado) -> None:
    assert normalizar_fuente(entrada) == esperado


def test_exporta_layout_con_nombre_interno_usa_la_familia() -> None:
    """Un bloque con font 'Arial-BoldMT' (nombre de PDF) sale en Arial, que Word sí encuentra."""
    b = _borrador("Texto.")
    b.layout = [
        {
            "texto": "Texto.",
            "align": "justify",
            "bold": False,
            "underline": False,
            "size_pt": 12,
            "font": "Arial-BoldMT",
            "heading": 0,
        }
    ]

    doc = Document(io.BytesIO(exportar_borrador_docx(b)))

    fuentes = {r.font.name for p in doc.paragraphs for r in p.runs if r.text.strip()}
    assert fuentes == {"Arial"}


def test_exporta_negrita_en_linea_y_saltos_de_linea() -> None:
    """**x** sale como run en negrita (sin asteriscos) y el "\\n" del bloque como salto de línea."""
    b = _borrador("x")
    b.layout = [
        {
            "texto": "por el **Artículo 194** del CPPM\nsegunda línea",
            "align": "justify",
            "bold": False,
            "underline": False,
            "size_pt": None,
            "font": None,
            "heading": 0,
        }
    ]

    doc = Document(io.BytesIO(exportar_borrador_docx(b)))

    p = next(p for p in doc.paragraphs if "Artículo 194" in p.text)
    assert "**" not in p.text
    negritas = [r.text for r in p.runs if r.bold]
    assert negritas == ["Artículo 194"]
    assert any("<w:br/>" in r._r.xml for r in p.runs)
    assert "segunda línea" in p.text


def test_contenido_md_con_negrita_en_linea() -> None:
    doc = Document(io.BytesIO(exportar_borrador_docx(_borrador("Texto con **clave** aquí."))))
    p = next(p for p in doc.paragraphs if "clave" in p.text)
    assert p.text == "Texto con clave aquí."
    assert [r.text for r in p.runs if r.bold] == ["clave"]
