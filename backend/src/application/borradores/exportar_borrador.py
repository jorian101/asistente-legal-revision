"""Use case: ExportarBorrador — convierte borrador a .docx con formato TSJM.

Aplica el formato canónico del tipo (meta.page: tamaño de hoja + márgenes;
esqueleto: alineación/negrita/tamaño del encabezado) sobre el contenido
markdown del borrador. Si no hay formato canónico, degrada a la conversión
plana previa (fuente Arial 12, párrafos sin estilo).
"""

from __future__ import annotations

import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt

from src.domain.entities.borrador import Borrador

# Tamaños de hoja en mm (carta, oficio, A4). Default carta.
TAMANOS_HOJA_MM = {
    "carta": (215.9, 279.4),
    "oficio": (215.9, 355.6),
    "a4": (210.0, 297.0),
}

# Márgenes legales TSJM en mm (izq/der/arriba/abajo).
MARGENES_DEFECTO_MM = (40.0, 20.0, 25.0, 20.0)

# Mapeo TipoBorrador -> tipo_documento del formato (para buscar el canónico).
TIPO_BORRADOR_A_FORMATO = {
    "dictamen_radicatoria": "dictamen_radicatoria",
    "proyecto_auto_vista_consulta": "auto_vista",
    "proyecto_auto_vista_apelacion": "auto_vista",
    "sugerencia_argumentacion": None,
}

_ALIGN = {
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "left": WD_ALIGN_PARAGRAPH.LEFT,
}


def _tamano_hoja(meta_page: dict) -> tuple[float, float]:
    """Devuelve (ancho_mm, alto_mm) desde meta.page; default carta."""
    # Si el formato trae tamaño explícito (carta/oficio/a4), respetarlo
    if "tamano_hoja" in meta_page and meta_page["tamano_hoja"] in TAMANOS_HOJA_MM:
        return TAMANOS_HOJA_MM[meta_page["tamano_hoja"]]
    # Si trae dimensiones reales (caso auto_vista 215.9x329.2), usarlas
    w = meta_page.get("width_mm")
    h = meta_page.get("height_mm")
    if w and h:
        return (float(w), float(h))
    # Fallback por clave o default carta
    clave = meta_page.get("tamano_hoja") or "carta"
    if clave in TAMANOS_HOJA_MM:
        return TAMANOS_HOJA_MM[clave]
    return TAMANOS_HOJA_MM["carta"]


def _margenes(meta_page: dict) -> tuple[float, float, float, float]:
    if meta_page.get("margin_left_mm") is not None:
        return (
            float(meta_page["margin_left_mm"]),
            float(meta_page.get("margin_right_mm", 20.0)),
            float(meta_page.get("margin_top_mm", 25.0)),
            float(meta_page.get("margin_bottom_mm", 20.0)),
        )
    return MARGENES_DEFECTO_MM


def normalizar_fuente(font: str | None) -> str | None:
    """Nombre interno de Word/PDF ("ArialMT", "Arial-BoldMT") -> familia instalable ("Arial").

    Sin esto, el .docx llevaba fuentes que Word no encuentra y sustituye (igual que el frontend,
    frontend/src/lib/fuentes.ts).
    """
    if not font:
        return None
    familia = re.sub(r"^[A-Z]{6}\+", "", font)
    familia = re.sub(
        r"[-,]?(BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular)?(PS)?MT$", "", familia
    )
    familia = re.sub(
        r"[-,](BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular)$", "", familia
    ).strip()
    if not familia:
        return None
    return familia if " " in familia else re.sub(r"([a-z])([A-Z])", r"\1 \2", familia)


_NEGRITA_EN_LINEA = re.compile(r"(\*\*[^*]+\*\*)")


def _escribir_texto(p: object, texto: str) -> None:
    """Texto del bloque -> runs: **negrita en línea** y "\n" como salto de línea.

    Misma convención que el editor (frontend/src/lib/textoBloque.ts). Antes se escribía el
    texto crudo y el .docx mostraba los ** literales.
    """
    lineas = texto.split("\n")
    for i, linea in enumerate(lineas):
        for tramo in _NEGRITA_EN_LINEA.split(linea):
            if not tramo:
                continue
            negrita = tramo.startswith("**") and tramo.endswith("**") and len(tramo) > 4
            run = p.add_run(tramo[2:-2] if negrita else tramo)  # type: ignore[attr-defined]
            if negrita:
                run.bold = True
        if i < len(lineas) - 1:
            p.add_run().add_break()  # type: ignore[attr-defined]


def _sin_marcas(texto: str) -> str:
    return texto.replace("**", "")


def _es_encabezado(linea: str) -> bool:
    s = linea.strip()
    # encabezados: markdown # o texto corto en mayúsculas sostenidas
    if s.startswith("#"):
        return True
    return len(s) <= 80 and s == s.upper() and any(c.isalpha() for c in s)


def _aplicar_estilo_parrafo(
    p: object,
    align: str | None,
    bold: bool | None,
    underline: bool | None,
    fuente: str,
    tamano_pt: float,
    size_pt_bloque: float | None = None,
    font_bloque: str | None = None,
) -> None:
    eff_fuente = normalizar_fuente(font_bloque) or fuente
    eff_pt = size_pt_bloque if size_pt_bloque is not None else tamano_pt
    for run in p.runs:  # type: ignore[attr-defined]
        run.font.name = eff_fuente  # type: ignore[attr-defined]
        run.font.size = Pt(eff_pt)  # type: ignore[attr-defined]
        if bold:
            run.bold = True  # type: ignore[attr-defined]
        if underline:
            run.underline = True  # type: ignore[attr-defined]
    if align and align in _ALIGN:
        p.alignment = _ALIGN[align]  # type: ignore[attr-defined]


def exportar_borrador_docx(borrador: Borrador, formato: object | None = None) -> bytes:
    """Genera un .docx aplicando el formato canónico (si existe) al contenido.

    Si borrador.layout existe (edicion fiel guardada), cada bloque del layout
    define su propio estilo (align/bold/size/font/heading). Si no, fallback a
    heuristica sobre contenido markdown (.md con # / ##).

    formato: FormatoDocumento con `meta` (page: tamaño/márgenes) y `esqueleto`.
    """
    document = Document()

    # Aplicar tamaño de hoja + márgenes desde el formato.
    fuente = "Arial"
    tamano_pt = 12
    if formato is not None and getattr(formato, "meta", None):
        meta = formato.meta or {}
        meta_page = meta.get("page") or {}
        meta_base = meta.get("base") or {}
        ancho, alto = _tamano_hoja(meta_page)
        izq, der, arr, aba = _margenes(meta_page)
        section = document.sections[0]
        section.page_width = Mm(ancho)
        section.page_height = Mm(alto)
        section.left_margin = Mm(izq)
        section.right_margin = Mm(der)
        section.top_margin = Mm(arr)
        section.bottom_margin = Mm(aba)
        if meta_base.get("font"):
            fuente = str(meta_base["font"])
        if meta_base.get("size_pt"):
            tamano_pt = float(meta_base["size_pt"])
    else:
        section = document.sections[0]
        section.page_width = Mm(215.9)
        section.page_height = Mm(279.4)
        section.left_margin = Mm(40)
        section.right_margin = Mm(20)
        section.top_margin = Mm(25)
        section.bottom_margin = Mm(20)

    layout = getattr(borrador, "layout", None)
    if layout:
        for bloque in layout:
            texto = (bloque.get("texto") or "").strip()
            if not texto:
                continue
            heading = bloque.get("heading") or 0
            if heading == 1:
                p = document.add_heading(_sin_marcas(texto), level=1)
            elif heading == 2:
                p = document.add_heading(_sin_marcas(texto), level=2)
            else:
                p = document.add_paragraph()
                _escribir_texto(p, texto)
            _aplicar_estilo_parrafo(
                p,
                align=bloque.get("align"),
                bold=bloque.get("bold"),
                underline=bloque.get("underline"),
                fuente=fuente,
                tamano_pt=tamano_pt,
                size_pt_bloque=bloque.get("size_pt"),
                font_bloque=bloque.get("font"),
            )
            # Si _aplicar no definio align (layout sin align), usar heuristica
            if not bloque.get("align"):
                if _es_encabezado(texto):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # type: ignore[attr-defined]
    else:
        # Fallback: heuristica sobre contenido .md
        for linea in borrador.contenido.splitlines():
            texto = linea.strip()
            if not texto:
                continue

            if texto.startswith("# "):
                p = document.add_heading(_sin_marcas(texto[2:].strip()), level=1)
            elif texto.startswith("## "):
                p = document.add_heading(_sin_marcas(texto[3:].strip()), level=2)
            else:
                p = document.add_paragraph()
                _escribir_texto(p, texto)

            # Aplicar estilo visual: encabezados centrados/negrita; resto justify.
            for run in p.runs:
                run.font.name = fuente
                run.font.size = Pt(tamano_pt)
            if _es_encabezado(texto):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.bold = True
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def resolver_contexto_export(formato: object | None) -> dict:
    """Resuelve tamano_hoja/margenes/fuente para la preview (mismo que export)."""
    fuente = "Arial"
    tamano_pt: float = 12
    tamano_hoja: str = "carta"
    margenes = {"top": 25, "right": 20, "bottom": 20, "left": 40}
    if formato is not None and getattr(formato, "meta", None):
        meta = formato.meta or {}  # type: ignore[union-attr]
        meta_page = meta.get("page") or {}
        meta_base = meta.get("base") or {}
        if meta_page.get("tamano_hoja") in TAMANOS_HOJA_MM:
            tamano_hoja = str(meta_page["tamano_hoja"])
        elif meta_page.get("width_mm") and meta_page.get("height_mm"):
            pass  # dimensiones reales: preview usa tamano_hoja
        if meta_page.get("margin_left_mm") is not None:
            margenes = {
                "top": float(meta_page.get("margin_top_mm", 25)),
                "right": float(meta_page.get("margin_right_mm", 20)),
                "bottom": float(meta_page.get("margin_bottom_mm", 20)),
                "left": float(meta_page.get("margin_left_mm", 40)),
            }
        if meta_base.get("font"):
            fuente = str(meta_base["font"])
        if meta_base.get("size_pt"):
            tamano_pt = float(meta_base["size_pt"])
    return {
        "tamano_hoja": tamano_hoja,
        "margenes": margenes,
        "font": fuente,
        "size_pt": tamano_pt,
    }
