"""Abreviatura única para las fuentes que suben los usuarios."""

from __future__ import annotations

import re
import unicodedata

PREFIJO_POR_CATEGORIA = {"norma": "LEY", "jurisprudencia": "JUR", "doctrina": "LIB"}
_MAX_SLUG = 40


def _slug(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", sin_tildes).strip("-").upper()[:_MAX_SLUG].strip("-")


async def generar_abreviatura(categoria: str, nombre: str, norma_repo) -> str:
    """`LIB-<SLUG>` (o LEY-/JUR-), con sufijo `-2`, `-3`... si ya existe."""
    try:
        prefijo = PREFIJO_POR_CATEGORIA[categoria]
    except KeyError as exc:
        raise ValueError(f"Categoría de fuente desconocida: {categoria!r}") from exc
    base = f"{prefijo}-{_slug(nombre) or 'SIN-NOMBRE'}"
    candidata, n = base, 1
    while await norma_repo.get_by_abreviatura(candidata) is not None:
        n += 1
        candidata = f"{base}-{n}"
    return candidata
