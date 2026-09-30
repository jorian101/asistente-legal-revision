"""Integracion (BD real): el CTE de get_ascendencia devuelve padres raiz.

Regresion: el paso recursivo exigia `f.padre_ref_id IS NOT NULL` sobre el
PADRE, asi que un padre raiz (sin abuelo) nunca entraba y la fase 4 no
ascendia nada (nodos_ascendidos = 0 en todo el historial). El unit test
simula session.execute y no ejecuta el SQL; este si.

Corre con `make test-integration`. Inserta una jerarquia propia dentro de
una transaccion que hace ROLLBACK: no deja filas en la BD.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl

pytestmark = pytest.mark.integration


async def _insertar_fragmento(s, norma_id: int, padre_id: int | None, nivel: int) -> int:
    return (
        await s.execute(
            text(
                "INSERT INTO fragmento (norma_id, qdrant_point_id, texto, padre_ref_id, "
                "nivel_jerarquico) VALUES (:n, :q, 'probe', :p, :nivel) RETURNING id"
            ),
            {"n": norma_id, "q": f"probe-{secrets.token_hex(8)}", "p": padre_id, "nivel": nivel},
        )
    ).scalar_one()


@pytest.mark.asyncio
@pytest.mark.timeout(30)  # conexion en frio (SCRAM) puede pasar el timeout global de 5 s
async def test_get_ascendencia_incluye_padre_raiz() -> None:
    from tests._bd_real import bd_real_asegurada

    with bd_real_asegurada() as settings:
        engine = create_async_engine(settings.postgres_url_async, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                s = AsyncSession(bind=conn)
                tag = secrets.token_hex(3).upper()
                norma_id = (
                    await s.execute(
                        text(
                            "INSERT INTO norma (nombre, abreviatura, tipo, jerarquia) "
                            "VALUES (:n, :a, 'ley_organica', 'militar') RETURNING id"
                        ),
                        {"n": f"Ley Probe {tag}", "a": f"ZPR{tag}"},
                    )
                ).scalar_one()
                # raiz (nivel 1) <- titulo (nivel 2) <- articulo (hoja, nivel 4)
                raiz = await _insertar_fragmento(s, norma_id, None, 1)
                titulo = await _insertar_fragmento(s, norma_id, raiz, 2)
                hoja = await _insertar_fragmento(s, norma_id, titulo, 4)
                # hoja cuyo padre directo es raiz (1006/1265 relaciones del corpus)
                hoja_de_raiz = await _insertar_fragmento(s, norma_id, raiz, 4)

                repo = FragmentoRepoImpl(s)
                cadena = {f.id for f in await repo.get_ascendencia([hoja], max_depth=3)}
                directa = {f.id for f in await repo.get_ascendencia([hoja_de_raiz], max_depth=3)}
                corta = {f.id for f in await repo.get_ascendencia([hoja], max_depth=2)}
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()

    assert cadena == {titulo, raiz}
    assert directa == {raiz}
    # la cota de profundidad sigue cortando la recursion
    assert corta == {titulo}
