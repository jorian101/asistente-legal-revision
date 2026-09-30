"""Domain service: categoría única de una fuente.

Pure domain logic. Hoy la categoría se decidía en cuatro sitios distintos
(prefijo de la abreviatura, jerarquía, tipo de documento, listas de tipos). Este
módulo es el único que la define:

- norma: leyes del corpus jurídico (siempre presentes en toda búsqueda).
- jurisprudencia: sentencias del TCP (SC/SCP) y de la CIDH, y los obrados de casos
  ya oficializados (autos de vista, ejemplo N4) y demás sentencias promovidas.
- doctrina: libros. Nunca leyes.
- obrado: documentos del expediente (privados o publicados).
"""

from __future__ import annotations

from typing import Literal

CategoriaFuente = Literal["norma", "jurisprudencia", "doctrina", "obrado"]

_POR_JERARQUIA: dict[str, CategoriaFuente] = {
    "suprema": "norma",
    "militar": "norma",
    "supletoria": "norma",
    "jurisprudencia": "jurisprudencia",
    "doctrina": "doctrina",
}

# Tipos de obra que no son un obrado del caso. `ejemplo` es el auto/dictamen
# oficializado (N4): jurisprudencia. `doctrina`, `doctrina_libro` y `material_caso`
# (alias deprecado del primero) son doctrina; `criterio` es instrucción, no fuente.
_POR_TIPO_DOCUMENTO: dict[str, CategoriaFuente] = {
    "jurisprudencia": "jurisprudencia",
    "ejemplo": "jurisprudencia",
    "doctrina": "doctrina",
    "doctrina_libro": "doctrina",
    "material_caso": "doctrina",
    "criterio": "doctrina",
    "norma_corpus": "norma",
}


def categoria_de_jerarquia(jerarquia: str) -> CategoriaFuente:
    """Categoría de una norma del corpus según su jerarquía."""
    try:
        return _POR_JERARQUIA[jerarquia]
    except KeyError as exc:
        raise ValueError(f"Jerarquía desconocida: {jerarquia!r}") from exc


def categoria_de_obra(tipo_documento: str) -> CategoriaFuente:
    """Categoría de una obra según su tipo de documento."""
    return _POR_TIPO_DOCUMENTO.get(tipo_documento, "obrado")


def tipo_fuente_de_obra(tipo_documento: str) -> str:
    """Valor de `tipo_fuente` del payload de Qdrant para una obra.

    Los obrados conservan 'obra' (valor histórico, sin migrar los puntos).
    """
    categoria = categoria_de_obra(tipo_documento)
    return "obra" if categoria == "obrado" else categoria


__all__ = [
    "CategoriaFuente",
    "categoria_de_jerarquia",
    "categoria_de_obra",
    "tipo_fuente_de_obra",
]
