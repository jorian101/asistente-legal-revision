"""Cache del vocabulario del corpus para la corrección de typos por edit-distance.

Carga UNA VEZ por proceso el conjunto de tokens únicos de 3+ caracteres
alfanuméricos presentes en los textos de los fragmentos (~19k tokens para
3.8k fragmentos). Se usa en HybridSearcher para corregir typos de la query
del usuario antes del embedding (Capa A, bug sala).

Patrón igual a config_cache.py: cache global en memoria, invalidation
explícita al reindexar el corpus.

Rendimiento:
- La query DISTINCT corre una sola vez (lazy en el primer request); los
  siguientes son cache hits (µs).
- La memoria es acotada: ~19k strings cortos, despreciable vs el corpus.
- Falla segura: el caller envuelve en try/except y degrada a no-corrección.
"""

from __future__ import annotations

import asyncio
import re

from sqlalchemy import text

# Solo tokens alfanuméricos de 3+ chars (excluye puntuación, números
# sueltos y ruido OCR que no aportan al edit-distance).
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9]{3,}$")

_vocabulario_cache: frozenset[str] | None = None
# La SQL tarda 8-13 s: quien llegue mientras otro la corre (p. ej. el
# precalentado del lifespan) espera su resultado en vez de repetirla.
_vocabulario_lock = asyncio.Lock()


async def get_vocabulario(session) -> frozenset[str]:
    """Retorna los tokens únicos del corpus, cacheados por proceso.

    La query recorre los textos de los fragmentos y extrae tokens únicos
    con regexp_split_to_table (LATERAL). Solo se ejecuta la primera vez;
    después se sirve desde la cache global.
    """
    global _vocabulario_cache
    if _vocabulario_cache is not None:
        return _vocabulario_cache

    async with _vocabulario_lock:
        if _vocabulario_cache is not None:
            return _vocabulario_cache
        tokens: set[str] = set()
        result = await session.execute(
            text(
                "SELECT DISTINCT lower(t) AS token "
                "FROM fragmento, LATERAL regexp_split_to_table(texto, '\\s+') AS t "
                "WHERE length(t) >= 3"
            )
        )
        for row in result:
            token = row[0]
            if _TOKEN_RE.match(token):
                tokens.add(token)
        _vocabulario_cache = frozenset(tokens)
        return _vocabulario_cache


def invalidate_vocabulario_cache() -> None:
    """Invalida la cache (llamar tras reindexar el corpus)."""
    global _vocabulario_cache
    _vocabulario_cache = None


__all__ = ["get_vocabulario", "invalidate_vocabulario_cache"]
