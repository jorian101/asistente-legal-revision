"""Segmentadores para Ley 1970 — Código Penal (CP) + Código Procesal Penal (CPP).

El PDF único contiene DOS códigos consolidados:
- CP: Artículo 1 a 364 (Código Penal)
- CPP: Artículo 1 a 442+ (Código Procesal Penal)

Boundary detection: buscar primer "Artículo 1..10" que aparezca DESPUÉS
de un "Artículo >= 350". Esa posición marca el inicio del CPP.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    clave_unica,
    enlazar_nodos_jerarquicos,
    particionar_articulo,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

# ----- Helpers comunes -----

# Encabezado de artículo: al inicio de línea o tras un punto (el PDF pierde el salto
# de línea en los cambios de página); una referencia como "conforme al artículo 39."
# no lo es. Con o sin tilde, sufijo opcional (Bis/Ter/...; grupo 2) y con punto o
# título entre paréntesis.
ARTICULO_RGX = re.compile(
    r"(?:^[ \t]*|(?<=[.;:] ))Art[ií]culo\s+(\d+)"
    r"(?:\s*\.?\s*(bis|ter|quater|quinquies)\b)?(?:\s*\.|(?=\s*\())",
    re.IGNORECASE | re.MULTILINE,
)

_ROMAN_ORDINAL = r"([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|[UÚ]NICO)"
_ROMAN_ORDINAL_EXT = (
    r"([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO"
    r"|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO|[UÚ]NICO)"
)
# Encabezados en mayúsculas y al inicio de línea: "Capítulo V como Capítulo VI" o
# "el Título IV del presente Código" son referencias, no estructura.
RGX_LIBRO = re.compile(r"^[ \t]*(?:LIBRO\s+" + _ROMAN_ORDINAL + ")", re.MULTILINE)
RGX_TITULO = re.compile(r"^[ \t]*(?:T[IÍ]TULO\s+" + _ROMAN_ORDINAL_EXT + ")", re.MULTILINE)
RGX_CAPITULO = re.compile(r"^[ \t]*(?:CAP[IÍ]TULO\s+" + _ROMAN_ORDINAL_EXT + ")", re.MULTILINE)
# "DISPOSICIONES TRANSITORIAS/FINALES..." cierran el articulado: lo que sigue al ultimo
# articulo (disposiciones, indices, avisos de la Gaceta) no es cuerpo de ese articulo.
RGX_DISPOSICIONES = re.compile(
    r"^[ \t]*DISPOSICI[OÓ]N(?:ES)?\s+(?:TRANSITORIAS?|FINALES|FINAL|ADICIONALES|ABROGATORIAS?"
    r"|DEROGATORIAS?)",
    re.MULTILINE,
)


def _cortes_estructurales(texto: str) -> list[int]:
    """Posiciones de los encabezados LIBRO/TÍTULO/CAPÍTULO/DISPOSICIONES, ordenadas."""
    rgxs = (RGX_LIBRO, RGX_TITULO, RGX_CAPITULO, RGX_DISPOSICIONES)
    return sorted(m.start() for rgx in rgxs for m in rgx.finditer(texto))


def _fin_articulo(inicio: int, fin: int, cortes: list[int]) -> int:
    """El cuerpo termina en el siguiente encabezado estructural si llega antes que `fin`."""
    i = bisect_right(cortes, inicio)
    return min(fin, cortes[i]) if i < len(cortes) else fin


def _padre_key(abreviatura: str, numero: int, sufijo: str) -> str:
    """`CP_13_MASTER`; con sufijo (Bis/Ter/...) `CP_13_BIS_MASTER`."""
    return (
        f"{abreviatura}_{numero}_{sufijo.upper()}_MASTER"
        if sufijo
        else (f"{abreviatura}_{numero}_MASTER")
    )


@dataclass(frozen=True, slots=True)
class _ArticuloPos:
    numero: int
    inicio: int


def _extraer_articulos(texto: str) -> list[_ArticuloPos]:
    """Extrae todos los artículos con su posición en el texto."""
    articulos: list[_ArticuloPos] = []
    for m in ARTICULO_RGX.finditer(texto):
        num = int(m.group(1))
        articulos.append(_ArticuloPos(numero=num, inicio=m.start()))
    return articulos


def _detectar_boundary(articulos: list[_ArticuloPos]) -> int:
    """
    Detecta la posición del boundary CP -> CPP.

    Estrategia: buscar primer artículo con número 1-10 que aparezca
    DESPUÉS de haber visto un artículo >= 350.
    """
    vio_alto = False
    for art in articulos:
        if art.numero >= 350:
            vio_alto = True
        if vio_alto and 1 <= art.numero <= 10:
            return art.inicio

    # Fallback: mayor caída en numeración
    for i in range(1, len(articulos)):
        if articulos[i - 1].numero - articulos[i].numero > 100:
            return articulos[i].inicio

    # Fallback final: el artículo de la mitad (posición de texto, no índice de lista)
    return articulos[len(articulos) // 2].inicio if articulos else 0


# ----- Segmentador CP (Codigo Penal) -----


class SegmentadorLey1970Cp(SegmentadorNorma):
    """Segmentador para el Código Penal ordinario (viene en el PDF de Ley 1970).

    Legal: el CP es el aprobado por Decreto Ley 10426 (1972), elevado a rango
    de Ley y modificado por la Ley 1768 (1997). Se agrupa con el CPP sólo porque
    comparten el PDF de consolidación, no la ley de origen.
    """

    ABREVIATURA = "CP"
    NOMBRE = (
        "Código Penal (Decreto Ley N\u00b0 10426 de 23 de agosto de 1972, "
        "elevado a rango de Ley y modificado por la Ley N\u00b0 1768 de 10 de marzo de 1997)"
    )
    REGEX_ARTICULO = ARTICULO_RGX

    REGEX_ESTRUCTURA = {
        "LIBRO": (RGX_LIBRO, 1),
        "TITULO": (RGX_TITULO, 2),
        "CAPITULO": (RGX_CAPITULO, 3),
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        texto = self._strip_basic(texto_completo)
        cortes = _cortes_estructurales(texto)

        # Extraer todos los articulos del PDF completo
        articulos = _extraer_articulos(texto)
        boundary_pos = _detectar_boundary(articulos)

        # CP = articulos antes del boundary
        art_matches = list(self.REGEX_ARTICULO.finditer(texto))
        cp_matches = [m for m in art_matches if m.start() < boundary_pos]

        nodos: dict[str, NodoJerarquico] = {}
        ocurrencias: list[tuple[int, str, int]] = []
        raices: list[str] = []
        fragmentos: list[FragmentoProducible] = []

        # Estructuras
        for clave_tipo, (rgx, nivel) in self.REGEX_ESTRUCTURA.items():
            for m in rgx.finditer(texto):
                if m.start() >= boundary_pos:
                    break  # Solo CP
                num_romano = m.group(1)
                titulo = m.group(0).strip()
                clave = clave_unica(nodos, f"CP_{clave_tipo}_{num_romano}")
                nodos[clave] = NodoJerarquico(
                    clave=clave,
                    nivel=nivel,
                    titulo=titulo,
                    hijos=[],
                    metadatos={"tipo_estructura": clave_tipo, "numero_romano": num_romano},
                )
                if nivel == 1:
                    raices.append(clave)
                ocurrencias.append((m.start(), clave, nivel))

        # D-S2C-06 split: enlazar padres/hijos (sin wiring de padre_ref_id)
        enlazar_nodos_jerarquicos(nodos, ocurrencias)

        # Artículos CP
        for i, m in enumerate(cp_matches):
            num_art = self._extraer_numero_articulo(m)
            if num_art == 0 or num_art > 364:
                continue

            inicio = m.start()
            fin = cp_matches[i + 1].start() if i + 1 < len(cp_matches) else boundary_pos
            fin = _fin_articulo(inicio, fin, cortes)
            texto_articulo = texto[inicio:fin].strip()

            cuerpo = self.REGEX_ARTICULO.sub("", texto_articulo, count=1).strip()
            sufijo = (m.group(2) or "").lower()
            padre_key = _padre_key("CP", num_art, sufijo)

            tipo_base = "articulo_simple" if len(cuerpo) < 800 else "articulo_multiparagrafo"
            partes = particionar_articulo(
                texto=cuerpo,
                abreviatura="CP",
                numero_articulo=num_art,
                tipo_base=tipo_base,
                padre_ref_key=padre_key,
            )
            if sufijo:
                for parte in partes:
                    parte.metadatos["sufijo"] = sufijo
            fragmentos.extend(partes)

        return ArbolJerarquico(
            abreviatura="CP",
            raices=raices,
            nodos=nodos,
            fragmentos=fragmentos,
        )


# ----- Segmentador CPP (Código Procesal Penal) -----


class SegmentadorLey1970Cpp(SegmentadorNorma):
    """Segmentador para el Código de Procedimiento Penal (Ley 1970, 1999)."""

    ABREVIATURA = "CPP"
    NOMBRE = "Código de Procedimiento Penal (Ley N\u00b0 1970 de 1999)"
    REGEX_ARTICULO = ARTICULO_RGX

    REGEX_ESTRUCTURA = {
        "LIBRO": (RGX_LIBRO, 1),
        "TITULO": (RGX_TITULO, 2),
        "CAPITULO": (RGX_CAPITULO, 3),
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        texto = self._strip_basic(texto_completo)
        cortes = _cortes_estructurales(texto)

        # Extraer todos los articulos del PDF completo
        articulos = _extraer_articulos(texto)
        boundary_pos = _detectar_boundary(articulos)

        # CPP = articulos desde el boundary en adelante
        art_matches = list(self.REGEX_ARTICULO.finditer(texto))
        cpp_matches = [m for m in art_matches if m.start() >= boundary_pos]

        nodos: dict[str, NodoJerarquico] = {}
        ocurrencias: list[tuple[int, str, int]] = []
        raices: list[str] = []
        fragmentos: list[FragmentoProducible] = []

        # Estructuras (solo después del boundary)
        for clave_tipo, (rgx, nivel) in self.REGEX_ESTRUCTURA.items():
            for m in rgx.finditer(texto):
                if m.start() < boundary_pos:
                    continue  # Solo CPP
                num_romano = m.group(1)
                titulo = m.group(0).strip()
                clave = clave_unica(nodos, f"CPP_{clave_tipo}_{num_romano}")
                nodos[clave] = NodoJerarquico(
                    clave=clave,
                    nivel=nivel,
                    titulo=titulo,
                    hijos=[],
                    metadatos={"tipo_estructura": clave_tipo, "numero_romano": num_romano},
                )
                if nivel == 1:
                    raices.append(clave)
                ocurrencias.append((m.start(), clave, nivel))

        # D-S2C-06 split: enlazar padres/hijos (sin wiring de padre_ref_id)
        enlazar_nodos_jerarquicos(nodos, ocurrencias)

        # D-S2C-06 split: enlazar padres/hijos (sin wiring de padre_ref_id)
        enlazar_nodos_jerarquicos(nodos, ocurrencias)

        # Artículos CPP
        for i, m in enumerate(cpp_matches):
            num_art = self._extraer_numero_articulo(m)
            if num_art == 0:
                continue

            inicio = m.start()
            fin = cpp_matches[i + 1].start() if i + 1 < len(cpp_matches) else len(texto)
            fin = _fin_articulo(inicio, fin, cortes)
            texto_articulo = texto[inicio:fin].strip()

            cuerpo = self.REGEX_ARTICULO.sub("", texto_articulo, count=1).strip()
            sufijo = (m.group(2) or "").lower()
            padre_key = _padre_key("CPP", num_art, sufijo)

            tipo_base = "articulo_simple" if len(cuerpo) < 800 else "articulo_multiparagrafo"
            partes = particionar_articulo(
                texto=cuerpo,
                abreviatura="CPP",
                numero_articulo=num_art,
                tipo_base=tipo_base,
                padre_ref_key=padre_key,
            )
            if sufijo:
                for parte in partes:
                    parte.metadatos["sufijo"] = sufijo
            fragmentos.extend(partes)

        return ArbolJerarquico(
            abreviatura="CPP",
            raices=raices,
            nodos=nodos,
            fragmentos=fragmentos,
        )


# Auto-registro (abreviatura canónica + alias histórico deprecado para
# compatibilidad de despliegue; retirar el alias tras la migración de payload).
SegmentadorRegistry.registrar("CP", SegmentadorLey1970Cp)
SegmentadorRegistry.registrar("CPP", SegmentadorLey1970Cpp)
