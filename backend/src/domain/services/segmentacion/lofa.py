"""Segmentador para LOFA — Ley Orgánica de las Fuerzas Armadas de la Nación.

Estructura observada en PDF (PyMuPDF RAW):
- ARTICULO Nº.- (SIEMPRE sin acento, con º y .-)
- 138 artículos reales
- Estructura: TÍTULO > CAPÍTULO > ARTÍCULO
"""

from __future__ import annotations

import re

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    enlazar_nodos_jerarquicos,
    particionar_articulo,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry


class SegmentadorLOFA(SegmentadorNorma):
    """Segmentador para LOFA (Ley Orgánica de las Fuerzas Armadas)."""

    ABREVIATURA = "LOFA"
    # ARTICULO/ARTÍCULO, número, ordinal (º/°/o — limpiar_texto_ocr normaliza º→o)
    REGEX_ARTICULO = re.compile(
        r"ART[IÍ]CULO\s+(\d+)[º°o]\.\-",
        re.IGNORECASE | re.MULTILINE,
    )

    REGEX_ESTRUCTURA = {
        "TITULO": (
            re.compile(
                r"T[IÍ]TULO\s+([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO|UNICO)",
                re.IGNORECASE,
            ),
            2,
        ),
        "CAPITULO": (
            re.compile(
                r"CAP[IÍ]TULO\s+([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO|UNICO)",
                re.IGNORECASE,
            ),
            3,
        ),
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        texto = self._strip_basic(texto_completo)

        nodos: dict[str, NodoJerarquico] = {}
        ocurrencias: list[tuple[int, str, int]] = []
        raices: list[str] = []

        # 1) Detectar estructuras (TÍTULO, CAPÍTULO)
        for clave_tipo, (rgx, nivel) in self.REGEX_ESTRUCTURA.items():
            for m in rgx.finditer(texto):
                num_romano = m.group(1)
                titulo = m.group(0).strip()
                clave = f"LOFA_{clave_tipo}_{num_romano}"
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

            cuerpo = self.REGEX_ARTICULO.sub("", texto_articulo, count=1).strip()
            padre_key = f"LOFA_{num_art}_MASTER"

            tipo_base = "articulo_simple" if len(cuerpo) < 800 else "articulo_multiparagrafo"
            partes = particionar_articulo(
                texto=cuerpo,
                abreviatura="LOFA",
                numero_articulo=num_art,
                tipo_base=tipo_base,
                padre_ref_key=padre_key,
            )
            fragmentos.extend(partes)

        return ArbolJerarquico(
            abreviatura="LOFA",
            raices=raices,
            nodos=nodos,
            fragmentos=fragmentos,
        )


# Auto-registro
SegmentadorRegistry.registrar("LOFA", SegmentadorLOFA)
