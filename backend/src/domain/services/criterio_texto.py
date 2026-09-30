"""Utilidades de texto de criterio (notas del vault sincronizadas a BD).

El seed seed_criterio_vault.py guarda el cuerpo de la nota sin el frontmatter
YAML (title/type/sources/tags...): el frontmatter es metadato interno del vault
y no debe llegar ni al prompt del LLM ni a la UI de Criterios.
"""

from __future__ import annotations


def strip_frontmatter(contenido: str) -> str:
    """Quita el bloque YAML inicial `--- ... ---` de una nota, si existe.

    Devuelve el cuerpo de la nota (sin la linea final de cierre del bloque).
    Si el contenido no arranca con `---`, se devuelve tal cual.
    """
    if not contenido.startswith("---"):
        return contenido
    fin = contenido.find("\n---", 3)
    if fin == -1:
        return contenido
    return contenido[fin + 4 :].lstrip("\n")
