"""Segmentadores para sentencias de la Corte IDH (Serie C).

Estructura de un fallo CIDH (tesis Tabla 19): encabezado jurisdiccional
(Corte, caso, fecha, jueces) + secciones delimitadas por numeración
romana (I, II, ...) con párrafos numerados en decimal + PUNTOS
RESOLUTIVOS al final.

- Encabezado -> nodo MAESTRO no indexable.
- Secciones de hechos/antecedentes/procedimiento -> bloque HECHO.
- PUNTOS RESOLUTIVOS / reparaciones / costas -> bloque FALLO.
- Resto (doctrina internacional y su aplicación a la Convención) ->
  bloque DERECHO.

Lo reutilizable es el estándar convencional, no el caso concreto.
"""

from __future__ import annotations

import re

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    enlazar_nodos_jerarquicos,
    partir_bloque_por_tamano,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

RGX_CASO = re.compile(r"Caso\s+(.+?)\s+Vs?\.\s*(.+)", re.IGNORECASE)
RGX_FECHA = re.compile(r"Sentencia de\s+(\d{1,2} de \w+ de \d{4})", re.IGNORECASE)
RGX_SERIE = re.compile(r"Serie\s+C\s+N[oº°]?\s*(\d+)", re.IGNORECASE)
# Sección romana: numeral + título en mayúsculas. Sin ancla ^ estricta:
# `limpiar_texto_ocr` puede fusionar la línea del numeral con la del
# título. El título exige 4+ mayúsculas para no tragar "II.1. ..." (tienen
# minúsculas/dígitos al inicio).
# Numeral solo en su línea + título en la siguiente, o numeral + título
# en la misma línea (limpiar_texto_ocr fusiona). Entre numeral y título
# se exige punto+salto o espacios: "LA CORTE" no matchea (sin separador
# tras la L).
RGX_SECCION = re.compile(
    r"(?:^|\n)\s*([IVXLCDM]+)(?:\.?\s*\n\s*|\s+)"
    r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ \(\)]{3,89})"
)
RGX_PARRAFO = re.compile(r"^(\d{1,4})\.\s", re.MULTILINE)

_PALABRAS_HECHO = (
    "HECHO",
    "ANTECEDENTE",
    "INTRODUCCI",
    "PROCEDIMIENTO",
    "TRÁMITE",
    "TRAMITE",
    "PRUEBA",
)
_PALABRAS_FALLO = (
    "RESOLUTIV",
    "REPARACI",
    "COSTAS",
    "FALLO",
    "PUNTOS",
)


def _clasificar_seccion(titulo: str) -> tuple[str, str]:
    """Título de sección -> (nombre_bloque, tipo_chunk)."""
    t = titulo.upper()
    if any(p in t for p in _PALABRAS_FALLO):
        return ("FALLO", "fundamentacion_del_fallo")
    if any(p in t for p in _PALABRAS_HECHO):
        return ("HECHO", "fundamento_de_hecho")
    return ("DERECHO", "fundamento_de_derecho_analisis")


class SegmentadorCIDHBase(SegmentadorNorma):
    """Base para fallos CIDH: la subclase fija ABREVIATURA/NOMBRE/FICHA."""

    ABREVIATURA = ""
    NOMBRE = ""
    METADATOS_FICHA: dict[str, str] = {}

    # Detector: cuenta SECCIONES romanas, no párrafos numerados (los
    # párrafos "1." existen en cualquier ley e inflarían matches ajenos).
    REGEX_ARTICULO = RGX_SECCION
    REGEX_ESTRUCTURA = {"SECCION": (RGX_SECCION, 1)}

    # NOTE: la base nunca se instancia (ABREVIATURA vacía -> TypeError
    # en __init__); cada fallo es una subclase que implementa segmentar.


def _segmentar_cidh(seg: SegmentadorCIDHBase, texto_completo: str) -> ArbolJerarquico:
    abrev = seg.ABREVIATURA
    texto = seg._strip_basic(texto_completo)

    secciones = list(RGX_SECCION.finditer(texto))
    if len(secciones) < 2:
        raise ValueError(f"Texto no parece fallo CIDH (sin secciones): {abrev}")

    nodos: dict[str, NodoJerarquico] = {}
    ocurrencias: list[tuple[int, str, int]] = []
    raices: list[str] = []
    fragmentos: list[FragmentoProducible] = []

    # Maestro no indexable: encabezado jurisdiccional.
    clave_maestro = f"{abrev}_MASTER"
    nodos[clave_maestro] = NodoJerarquico(
        clave=clave_maestro,
        nivel=1,
        titulo=f"Corte IDH — {seg.METADATOS_FICHA.get('caso', abrev)}",
        hijos=[],
        metadatos={
            "tipo_estructura": "MAESTRO_CIDH",
            "no_indexable": True,
            **seg.METADATOS_FICHA,
        },
    )
    raices.append(clave_maestro)

    for i, sm in enumerate(secciones):
        fin = secciones[i + 1].start() if i + 1 < len(secciones) else len(texto)
        titulo = sm.group(2).strip()
        nombre_bloque, tipo_chunk = _clasificar_seccion(titulo)
        clave_nodo = f"{abrev}_{nombre_bloque}_{sm.group(1)}"
        cuerpo = texto[sm.start() : fin].strip()
        nodos[clave_nodo] = NodoJerarquico(
            clave=clave_nodo,
            nivel=2,
            titulo=titulo,
            hijos=[],
            metadatos={"tipo_estructura": f"BLOQUE_{nombre_bloque}"},
        )
        ocurrencias.append((sm.start(), clave_nodo, 2))

        for j, parte in enumerate(partir_bloque_por_tamano(cuerpo)):
            suf = "" if j == 0 else f"-p{j + 1}"
            fragmentos.append(
                FragmentoProducible(
                    texto=parte,
                    nivel_jerarquico=4,
                    tipo_chunk=tipo_chunk,
                    padre_ref_key=f"{clave_nodo}{suf}",
                    metadatos={
                        "bloque": nombre_bloque.lower(),
                        "seccion": titulo,
                        "numero_sentencia": abrev,
                    },
                )
            )

    enlazar_nodos_jerarquicos(nodos, ocurrencias)
    return ArbolJerarquico(abreviatura=abrev, raices=raices, nodos=nodos, fragmentos=fragmentos)


class SegmentadorCIDHTcPeru(SegmentadorCIDHBase):
    """Caso Tribunal Constitucional vs Perú (Serie C 71, 2001)."""

    ABREVIATURA = "CIDH-TC-PERU-2001"
    NOMBRE = "Corte IDH — Caso Tribunal Constitucional vs Perú (Serie C N° 71, 31 de enero de 2001)"
    METADATOS_FICHA = {
        "numero": "Serie C N° 71",
        "organo": "Corte Interamericana de Derechos Humanos",
        "caso": "Tribunal Constitucional vs Perú",
        "fecha": "2001-01-31",
        "materia": "garantias_judiciales",
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_cidh(self, texto_completo)


SegmentadorRegistry.registrar("CIDH-TC-PERU-2001", SegmentadorCIDHTcPeru)
