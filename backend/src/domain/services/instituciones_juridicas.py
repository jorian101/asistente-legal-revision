"""Domain service: consultas dirigidas por institución jurídica o artículo explícito.

Pure domain logic. La búsqueda semántica sola no relaciona «debido proceso» con
el Art. 115 CPE ni «artículo 115 de la CPE» con su fragmento (el embedding no
distingue números). Este servicio devuelve consultas `(query, filtros_payload)`
con `abreviatura` + `numero_articulo`, el mismo mecanismo determinista que
`queries_competencia`: recuperan el artículo exacto sin umbral de score.

Orden = jerarquía del vocal: constitución primero, Ley 1970 (CPP) supletoria al
final; nunca desplaza a la CPE. Solo se listan artículos verificados en el
corpus indexado (CPE 115/116/117/119, CPP 1/5/6).
"""

from __future__ import annotations

import re

Consulta = tuple[str, dict]

# Peso en la fusión RRF de un artículo pedido por su número: es lo que el usuario
# quiere y debe ir por delante del ruido semántico de la búsqueda principal.
_PESO_EXPLICITO = 3.0

# (patrón de la consulta, ((abreviatura, artículo, texto para el embedding), ...))
_INSTITUCIONES: tuple[tuple[re.Pattern[str], tuple[tuple[str, int, str], ...]], ...] = (
    (
        re.compile(r"\bdebido\s+proceso\b", re.IGNORECASE),
        (
            ("CPE", 115, "derecho al debido proceso, a la defensa y a una justicia plural"),
            (
                "CPE",
                117,
                "nadie puede ser condenado sin haber sido oído y juzgado en debido proceso",
            ),
            ("CPP", 1, "ninguna condena sin juicio previo y proceso legal"),
        ),
    ),
    (
        re.compile(r"\bpresunci[oó]n\s+de\s+inocencia\b", re.IGNORECASE),
        (
            ("CPE", 116, "se garantiza la presunción de inocencia"),
            ("CPP", 6, "presunción de inocencia del imputado"),
        ),
    ),
    (
        re.compile(r"\bderecho\s+a\s+la\s+defensa\b", re.IGNORECASE),
        (
            ("CPE", 119, "derecho inviolable a la defensa"),
            ("CPP", 5, "calidad y derechos del imputado"),
        ),
    ),
)

# Abreviatura en la consulta -> abreviatura del corpus.
_ALIAS_NORMA = {
    "cpe": "CPE",
    "constitución": "CPE",
    "constitucion": "CPE",
    "cpp": "CPP",
    "ley 1970": "CPP",
    "cppm": "CPPM",
    "cpm": "CPM",
    "código penal militar": "CPM",
    "codigo penal militar": "CPM",
    "lojm": "LOJM",
    "lofa": "LOFA",
}
_ALIAS_RE = "|".join(re.escape(a) for a in sorted(_ALIAS_NORMA, key=len, reverse=True))
# «art. 178 del CPM» (norma tras preposición) o «Art. 179.I CPE» (sigla pegada al
# número, parágrafo romano opcional), como la escribe el criterio del vocal.
_ARTICULO_EXPLICITO = re.compile(
    rf"\bart(?:[ií]culos?|s?\.)?\s*(\d{{1,4}})(?:\s*(?:bis|ter))?"
    rf"(?:(?:[^.\n]{{0,40}}?)\b(?:de\s+la|del|de)\s+(?:la\s+)?|(?:\.[IVX]{{1,4}})?\s+)"
    rf"({_ALIAS_RE})\b",
    re.IGNORECASE,
)


def articulos_explicitos(texto: str) -> tuple[tuple[str, int], ...]:
    """(abreviatura, artículo) citados literalmente en el texto, sin duplicados y en orden."""
    vistos: dict[tuple[str, int], None] = {}
    for match in _ARTICULO_EXPLICITO.finditer(texto):
        vistos.setdefault((_ALIAS_NORMA[match.group(2).lower()], int(match.group(1))), None)
    return tuple(vistos)


def consultas_dirigidas(consulta: str) -> tuple[Consulta, ...]:
    """Consultas `(query, {abreviatura, numero_articulo})` para la consulta dada."""
    vistas: set[tuple[str, int]] = set()
    resultado: list[Consulta] = []

    def _agregar(abreviatura: str, articulo: int, texto: str, peso: float | None = None) -> None:
        if (abreviatura, articulo) in vistas:
            return
        vistas.add((abreviatura, articulo))
        filtros: dict = {"abreviatura": abreviatura, "numero_articulo": articulo}
        if peso is not None:
            filtros["peso_rrf"] = peso
        resultado.append((texto, filtros))

    for abreviatura, articulo in articulos_explicitos(consulta):
        _agregar(abreviatura, articulo, f"artículo {articulo} {abreviatura}", _PESO_EXPLICITO)

    for patron, articulos in _INSTITUCIONES:
        if patron.search(consulta):
            for abreviatura, articulo, texto in articulos:
                _agregar(abreviatura, articulo, texto)

    return tuple(resultado)


__all__ = ["articulos_explicitos", "consultas_dirigidas"]
