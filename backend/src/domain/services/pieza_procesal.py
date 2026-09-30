"""Pieza procesal que nombra una consulta sobre el expediente (ADR-005, seccion B).

«¿Que dictamino el auditor?» pide el dictamen, no las diez obras del expediente. El mapa sale
de la tabla de tipos de documento del ADR-005 —quien genera cada pieza y que contiene—, no de
las preguntas del golden de evaluacion: asi el alcance no se ajusta al resultado que se mide.
"""

from __future__ import annotations

import re

# (patron, tipos de documento). Cada fila cita la definicion del ADR-005 de la que sale.
_PIEZAS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    # sentencia: «Sentencia N° X con sentido (condenatoria/absolutoria) ... fallo» (TPJM).
    (re.compile(r"\bsentencia\b|\bfallo\b", re.IGNORECASE), frozenset({"sentencia"})),
    # auto_interlocutorio: «Resolucion incidental recurrida», p. ej. la que declara infundada
    # una excepcion de prescripcion.
    (
        re.compile(
            r"\bauto\s+interlocutorio\b|\bresoluci[oó]n\s+(incidental|apelada|recurrida)\b"
            r"|\bexcepci[oó]n\b",
            re.IGNORECASE,
        ),
        frozenset({"auto_interlocutorio"}),
    ),
    # memorial_apelacion: «Recurso de Apelacion Incidental: agravios, fundamentos, peticiones».
    (
        re.compile(
            r"\bagravios?\b|\bmemorial\s+de\s+apelaci[oó]n\b|\brecurso\s+de\s+apelaci[oó]n\b",
            re.IGNORECASE,
        ),
        frozenset({"memorial_apelacion"}),
    ),
    # oficio_elevacion: «Oficio administrativo que eleva obrados al TSJM».
    (
        re.compile(r"\boficio\s+de\s+elevaci[oó]n\b", re.IGNORECASE),
        frozenset({"oficio_elevacion"}),
    ),
    # acta_audiencia: «Acta de audiencia de juicio oral».
    (
        re.compile(r"\bacta\b|\bjuicio\s+oral\b", re.IGNORECASE),
        frozenset({"acta_audiencia"}),
    ),
    # requerimiento_fiscal: «Dictamen fiscal que pide confirmar/revocar» (Fiscal Militar).
    (
        re.compile(r"\bfiscal\b|\brequerimiento\b", re.IGNORECASE),
        frozenset({"requerimiento_fiscal"}),
    ),
    # dictamen_radicatoria y dictamen_fondo: los dos los emite el Auditor de la SAC.
    (
        re.compile(r"\bauditor\b|\bdictamen\b|\bdictamin[oó]\b", re.IGNORECASE),
        frozenset({"dictamen_radicatoria", "dictamen_fondo"}),
    ),
    # relacion_obrados: «Resumen cronologico del expediente» (Vocal Relator).
    (
        re.compile(r"\brelaci[oó]n\s+de\s+obrados\b", re.IGNORECASE),
        frozenset({"relacion_obrados"}),
    ),
)


def tipos_nombrados(consulta: str) -> frozenset[str]:
    """Tipos de documento de las piezas que la consulta nombra (vacio si no nombra ninguna)."""
    return frozenset().union(*(tipos for patron, tipos in _PIEZAS if patron.search(consulta)))


# SIN USO. La politica de preguntas amplias (acotarlas a las obras de sintesis de su via) se
# midio y NO paso el criterio de aceptacion: bajaba la cobertura del golden a 0,760 y la de la
# validacion independiente a 0,866 (commit 7c66144; docs/evaluacion/criterio-aceptacion.md).
# No encenderla creyendo que quedo pendiente: queda como registro de que se probo.
# Pregunta por el caso en su conjunto (politica de preguntas amplias, criterio 1:
# docs/evaluacion/politica-preguntas-amplias.md). Solo las formas que lista la politica.
_CASO_EN_CONJUNTO = re.compile(
    r"\bde\s+qu[eé]\s+trata\b|\bres[uú]m(en|ir|[ií])\b|\bhechos\b|\bsituaci[oó]n\s+jur[ií]dica\b"
    r"|\bqui[eé]n\s+es\s+el\s+procesado\b|\bimputaci[oó]n\b",
    re.IGNORECASE,
)


def es_pregunta_amplia(consulta: str) -> bool:
    """Pide el caso en su conjunto y no nombra ninguna pieza procesal."""
    return not tipos_nombrados(consulta) and bool(_CASO_EN_CONJUNTO.search(consulta))
