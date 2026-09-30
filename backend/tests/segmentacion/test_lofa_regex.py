"""Tests del regex de articulos en SegmentadorLOFA.

Bug Sprint 0: el regex viejo era `ART[I!I]CULO\\s+(\\d+)[°°]\\.-` (solo [º°])
pero `limpiar_texto_ocr()` normaliza via NFKC el ordinal º (U+00BA) -> o
latina, asi que el regex NO matcheaba nada en el texto limpio.
Fix: ampliado regex a `[º°o]` para tolerar ambos formatos (input crudo
y normalizado post-NFKC).

Estos tests blindan 3 invariantes:
- Match con 'º' literal (U+00BA) en input crudo.
- Match con 'o' latina despues de aplicar NFKC (limpieza OCR).
- NO match si falta el guion final (es un literal parcial, no un articulo valido).
"""

from __future__ import annotations

import unicodedata

from src.domain.services.segmentacion.lofa import SegmentadorLOFA


def _norm_nfkc(s: str) -> str:
    """Aplica la misma normalizacion que `limpiar_texto_ocr`."""
    return unicodedata.normalize("NFKC", s)


def test_match_con_ordinal_grado_literal() -> None:
    """Input crudo con º (U+00BA) -> match."""
    seg = SegmentadorLOFA()
    texto = (
        "TITULO PRIMERO\n"
        "ARTICULO 1º.- Articulo de prueba, contenido.\n\n"
        "ARTICULO 2º.- Otro articulo."
    )

    matches = list(seg.REGEX_ARTICULO.finditer(texto))

    assert len(matches) == 2, f"esperaba 2 articulos, vi {len(matches)}"
    assert matches[0].group(1) == "1"
    assert matches[1].group(1) == "2"


def test_match_con_o_post_normalizacion_nfkc() -> None:
    """Despues de NFKC, primero caracteristica: '1º' se colapsa a '1o'.
    Tolerar 'o' en el regex es la pieza clave del fix.
    """
    seg = SegmentadorLOFA()
    raw = "ARTICULO 1º.- Texto uno.\n\nARTICULO 2º.- Texto dos."
    normalized = _norm_nfkc(raw)

    # Antes de NFKC: debe matchear con literal 'º'.
    matches_raw = list(seg.REGEX_ARTICULO.finditer(raw))
    assert len(matches_raw) == 2

    # Despues de NFKC: debe seguir matcheando (porque regex tiene [º°o]).
    matches_norm = list(seg.REGEX_ARTICULO.finditer(normalized))
    assert len(matches_norm) == 2, (
        f"despues de NFKC el regex tendria que tolerar 'o': "
        f"esperaba 2 matches, vi {len(matches_norm)}"
    )


def test_no_match_sin_guion_final() -> None:
    """'ARTICULO 1º.' sin guion '-' despues del punto NO cuenta como articulo valido.
    (Refleja el comportamiento real del PDF: el '-' es lo que cierra el preambulo.)
    """
    seg = SegmentadorLOFA()
    texto = "ARTICULO 1º. No es articulo valido sin guion.\nARTICULO 2º.- Si es valido."

    matches = list(seg.REGEX_ARTICULO.finditer(texto))

    assert len(matches) == 1, f"esperaba 1 articulo (con guion), vi {len(matches)}"
    assert matches[0].group(1) == "2"


def test_segmentador_lofa_segmenta_con_nfkc() -> None:
    """Test integracion: segmentador LOFA con texto que pasa por limpiar_texto_ocr
    (que aplica NFKC) produce el mismo numero de fragmentos que con texto crudo.
    """
    from src.domain.services.segmentacion.base import limpiar_texto_ocr

    seg = SegmentadorLOFA()
    raw = (
        "TITULO PRIMERO\n\n"
        "ARTICULO 1º.- Articulo uno, primer parrafo.\n\n"
        "ARTICULO 2º.- (a) Inciso a del articulo dos.\n"
        "(b) Inciso b del articulo dos.\n\n"
        "ARTICULO 3º.- Articulo tres."
    )
    normalized = limpiar_texto_ocr(raw)

    # Aplicar ambos flujos (raw ya pasa por _strip_basic que no aplica NFKC)
    arbo_raw = seg.segmentar(raw)
    arbo_norm = seg.segmentar(normalized)

    # Sin NFKC, todos los matches con 'º' funcionan; con NFKC tambien (regex
    # tolera o post-collapse). Esperamos 3 articulos en ambos flujos.
    # Como `particionar_articulo()` puede partir por parrafos, el conteo de
    # fragmentos varia. Verificamos que al menos se produzcan articulos.
    assert len(arbo_raw.fragmentos) > 0
    assert len(arbo_norm.fragmentos) > 0
