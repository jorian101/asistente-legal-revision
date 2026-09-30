"""Segmentador para CPE — Constitución Política del Estado.

Estructura observada en PDF (PyMuPDF RAW):
- Artículo N. (TÍTULO) — Texto
- 411 artículos reales
- Estructura: PARTE > TÍTULO > CAPÍTULO > SECCIÓN > ARTÍCULO
"""

from __future__ import annotations

import re

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

_ORD_PARTE = r"PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[EÉ]PTIMA|OCTAVA|NOVENA|D[EÉ]CIMA"


class SegmentadorCPE(SegmentadorNorma):
    """Segmentador para CPE (Constitución Política del Estado)."""

    ABREVIATURA = "CPE"
    # Artículo N. al inicio de línea o tras un punto; "el artículo 339.I de esta
    # Constitución" o "Artículo 234.7" dentro de una frase son referencias.
    REGEX_ARTICULO = re.compile(
        r"(?:^[ \t]*|(?<=[.;:] ))Artículo\s+(\d+)\.(?![\dIVX])", re.IGNORECASE | re.MULTILINE
    )

    # Encabezados en mayúsculas y al inicio de línea: "el Título IV del presente" es una
    # referencia. En el PDF real las Partes son "PRIMERA PARTE" (se acepta "PARTE PRIMERA").
    REGEX_ESTRUCTURA = {
        "PARTE": (
            re.compile(
                rf"^[ \t]*(?:PARTE\s+(?={_ORD_PARTE}\b)|(?={_ORD_PARTE}\s+PARTE\b))({_ORD_PARTE})",
                re.MULTILINE,
            ),
            1,
        ),
        "TITULO": (
            re.compile(
                r"^[ \t]*T[IÍ]TULO\s+([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO"
                r"|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO|[UÚ]NICO)",
                re.MULTILINE,
            ),
            2,
        ),
        "CAPITULO": (
            re.compile(
                r"^[ \t]*CAP[IÍ]TULO\s+([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO"
                r"|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO|[UÚ]NICO)",
                re.MULTILINE,
            ),
            3,
        ),
        "SECCION": (
            re.compile(
                r"^[ \t]*SECCI[OÓ]N\s+([IVX]+|PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA"
                r"|S[EÉ]PTIMA|OCTAVA|NOVENA|D[EÉ]CIMA)",
                re.MULTILINE,
            ),
            3,
        ),
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        texto = self._strip_basic(texto_completo)

        nodos: dict[str, NodoJerarquico] = {}
        ocurrencias: list[tuple[int, str, int]] = []
        raices: list[str] = []

        # 1) Detectar estructuras jerárquicas
        for clave_tipo, (rgx, nivel) in self.REGEX_ESTRUCTURA.items():
            for m in rgx.finditer(texto):
                num_romano = m.group(1)
                titulo = m.group(0).strip()
                clave = clave_unica(nodos, f"CPE_{clave_tipo}_{num_romano}")
                nodos[clave] = NodoJerarquico(
                    clave=clave,
                    nivel=nivel,
                    titulo=titulo,
                    hijos=[],
                    metadatos={"tipo_estructura": clave_tipo, "numero_romano": num_romano},
                )
                ocurrencias.append((m.start(), clave, nivel))
                if nivel == 1:
                    raices.append(clave)

        # D-S2C-06 split: enlazar padres/hijos (sin wiring de padre_ref_id)
        enlazar_nodos_jerarquicos(nodos, ocurrencias)

        # 2) Detectar y particionar artículos
        fragmentos: list[FragmentoProducible] = []
        art_matches = list(self.REGEX_ARTICULO.finditer(texto))

        for i, m in enumerate(art_matches):
            num_art = self._extraer_numero_articulo(m)
            if num_art == 0:
                continue

            inicio = m.start()
            fin = art_matches[i + 1].start() if i + 1 < len(art_matches) else len(texto)
            texto_articulo = texto[inicio:fin].strip()

            # Quitar cabecera "Artículo N. ..."
            cuerpo = self.REGEX_ARTICULO.sub("", texto_articulo, count=1).strip()
            padre_key = f"CPE_{num_art}_MASTER"

            tipo_base = "articulo_simple" if len(cuerpo) < 800 else "articulo_multiparagrafo"
            partes = particionar_articulo(
                texto=cuerpo,
                abreviatura="CPE",
                numero_articulo=num_art,
                tipo_base=tipo_base,
                padre_ref_key=padre_key,
            )
            fragmentos.extend(partes)

        return ArbolJerarquico(
            abreviatura="CPE",
            raices=raices,
            nodos=nodos,
            fragmentos=fragmentos,
        )


# Auto-registro
SegmentadorRegistry.registrar("CPE", SegmentadorCPE)
