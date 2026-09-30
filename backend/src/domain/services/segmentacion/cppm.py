"""Segmentador para CPPM — Código de Procedimiento Penal Militar.

Estructura observada en PDF (PyMuPDF RAW):
- ARTÍCULO N°— (TÍTULO). — Texto
- Variantes: °—, °-, º—
- 248 artículos reales (1-263, con saltos por derogados)
- Estructura: LIBRO > TÍTULO > CAPÍTULO > ARTÍCULO
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


class SegmentadorCPPM(SegmentadorNorma):
    """Segmentador para CPPM (Código de Procedimiento Penal Militar)."""

    ABREVIATURA = "CPPM"
    # Variantes observadas en PDF: ARTÍCULO 189°— (º), ARTÍCULO 194o— (o).
    # `limpiar_texto_ocr` normaliza NFKC: º (U+00BA) -> o latina, asi que el
    # regex debe tolerar ambos (mismo patron que SegmentadorLOFA).
    REGEX_ARTICULO = re.compile(r"ART[IÍ]CULO\s+(\d+)[º°o]?\s*[—\-]", re.IGNORECASE | re.MULTILINE)

    REGEX_ESTRUCTURA = {
        "LIBRO": (
            re.compile(
                r"LIBRO\s+([IVX]+|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO)",
                re.IGNORECASE,
            ),
            1,
        ),
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
        fragmentos: list[FragmentoProducible] = []

        # 1) Detectar estructuras (LIBRO, TÍTULO, CAPÍTULO)
        for clave_tipo, (rgx, nivel) in self.REGEX_ESTRUCTURA.items():
            for m in rgx.finditer(texto):
                num_romano = m.group(1)
                titulo = m.group(0).strip()
                clave = f"CPPM_{clave_tipo}_{num_romano}"
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

        # 2) Detectar artículos y particionar
        # Encontrar posiciones de todos los artículos
        art_matches = list(self.REGEX_ARTICULO.finditer(texto))
        for i, m in enumerate(art_matches):
            num_art = self._extraer_numero_articulo(m)
            if num_art == 0:
                continue

            inicio = m.start()
            fin = art_matches[i + 1].start() if i + 1 < len(art_matches) else len(texto)
            texto_articulo = texto[inicio:fin].strip()

            # Quitar cabecera "ARTÍCULO N°— ..." para dejar solo el cuerpo
            cuerpo = self.REGEX_ARTICULO.sub("", texto_articulo, count=1).strip()

            # Clave maestra del artículo (el wiring a la estructura va en s5;
            # el stub anterior siempre devolvía None: mismo comportamiento).
            padre_key = f"CPPM_{num_art}_MASTER"

            # Particionar artículo en fragment(s)
            partes = particionar_articulo(
                texto=cuerpo,
                abreviatura="CPPM",
                numero_articulo=num_art,
                tipo_base="articulo_simple" if len(cuerpo) < 800 else "articulo_multiparagrafo",
                padre_ref_key=padre_key,
            )

            fragmentos.extend(partes)

        return ArbolJerarquico(
            abreviatura="CPPM",
            raices=raices,
            nodos=nodos,
            fragmentos=fragmentos,
        )


# Auto-registro
SegmentadorRegistry.registrar("CPPM", SegmentadorCPPM)
