"""Tests del regex de articulos en SegmentadorCPPM — variante ordinal 'o'.

Bug P2.1: el PDF del CPPM mezcla dos variantes de ordinal en los encabezados
de articulo: `º` (U+00BA) y `o` (U+006F, letra latina). `limpiar_texto_ocr()`
normaliza via NFKC el ordinal `º` -> `o`, por lo que el regex viejo
`[º°]?` NO matcheaba los articulos 190-197 ni el 194 (consulta de oficio).
Esto dejo 79 articulos del CPPM sin indexar (incluido el Art. 194 CPPM,
base normativa de la consulta de oficio).

Fix: ampliado regex a `[º°o]?` (mismo patron que SegmentadorLOFA).

Estos tests blindan 2 invariantes:
- Match con variante 'o' post-NFKC (input normalizado por limpiar_texto_ocr).
- Match con 'º' literal en input crudo.
"""

from __future__ import annotations

import unicodedata

from src.domain.services.segmentacion.cppm import SegmentadorCPPM


def _norm_nfkc(s: str) -> str:
    """Aplica la misma normalizacion que `limpiar_texto_ocr`."""
    return unicodedata.normalize("NFKC", s)


def test_cppm_matchea_articulo_194_con_o_post_nfkc() -> None:
    """Regresion P2.1: Art. 194 (consulta de oficio) debe detectarse tras NFKC."""
    seg = SegmentadorCPPM()
    raw = (
        "ARTÍCULO 189°— (Audiencia pública).— El día y hora señalados.\n\n"
        "ARTÍCULO 194º— (Consulta).— Al no ser apelada la sentencia en el "
        "término de ley, el Tribunal ordenará se remita obrados en consulta."
    )
    normalized = _norm_nfkc(raw)

    matches_raw = list(seg.REGEX_ARTICULO.finditer(raw))
    matches_norm = list(seg.REGEX_ARTICULO.finditer(normalized))

    assert [m.group(1) for m in matches_raw] == ["189", "194"], (
        f"crudo: esperaba [189, 194], vi {[m.group(1) for m in matches_raw]}"
    )
    assert [m.group(1) for m in matches_norm] == ["189", "194"], (
        f"post-NFKC: esperaba [189, 194], vi {[m.group(1) for m in matches_norm]}"
    )


def test_cppm_segmentador_captura_articulo_194_con_limpiar_texto_ocr() -> None:
    """Integracion: limpiar_texto_ocr + segmentar debe producir el Art. 194."""
    from src.domain.services.segmentacion.base import limpiar_texto_ocr

    seg = SegmentadorCPPM()
    raw = (
        "ARTÍCULO 189°— (Audiencia pública).— El día y hora señalados por la "
        "Presidencia del Tribunal, se procederá a la lectura.\n\n"
        "ARTÍCULO 194º— (Consulta).— Al no ser apelada la sentencia en el "
        "término de ley, el Tribunal ordenará se remita obrados en consulta."
    )
    normalized = limpiar_texto_ocr(raw)

    arbol = seg.segmentar(normalized)
    arts = {f.metadatos.get("numero_articulo") for f in arbol.fragmentos}

    assert 189 in arts and 194 in arts, f"esperaba arts. 189 y 194, vi {sorted(arts)}"


def test_cppm_matchea_variante_o_sin_guion_adicional() -> None:
    """Variante 'o' directa (sin NFKC de por medio) tambien debe matchear."""
    seg = SegmentadorCPPM()
    texto = "ARTÍCULO 190o— (Asistencia).— Estará presente el defensor."
    matches = list(seg.REGEX_ARTICULO.finditer(texto))
    assert len(matches) == 1
    assert matches[0].group(1) == "190"
