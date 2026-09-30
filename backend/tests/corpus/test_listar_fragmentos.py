"""Tests unitarios del caso de uso ListarFragmentos.

TDD: mockea el port FragmentoRepo (sin DB real). Verifica filtros, paginacion
y clamps del use case, no la implementacion SQL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.listar_fragmentos import (
    MAX_POR_PAGINA,
    ListarFragmentos,
    ListarFragmentosRequest,
)
from src.application.ports.fragmento_repo import PaginaFragmentos


def _fragmento_mock(
    fid: int = 1,
    norma_id: int = 1,
    qp: str = "uuid-1",
    texto: str = "texto",
    chunk: str = "articulo_simple",
    nivel: int = 4,
):
    m = MagicMock()
    m.id = fid
    m.norma_id = norma_id
    m.obra_id = None
    m.expediente_id = None
    m.qdrant_point_id = qp
    m.texto = texto
    m.padre_ref_id = None
    m.padre_ref_key = f"PADRE_{fid}"
    m.nivel_jerarquico = nivel
    m.metadatos = {"tipo_chunk": chunk}
    m.tipo_chunk = chunk
    return m


def _repo_returning(items: list, total: int, pagina: int = 1) -> MagicMock:
    repo = MagicMock()
    repo.list_fragmentos = AsyncMock(
        return_value=PaginaFragmentos(
            items=items,
            total=total,
            pagina=pagina,
            por_pagina=10,
        )
    )
    return repo


@pytest.mark.asyncio
async def test_devuelve_pagina_con_filtros() -> None:
    """Pasa pagina+por_pagina y filtros al repo; devuelve DTO con total."""
    frags = [_fragmento_mock(1), _fragmento_mock(2)]
    repo = _repo_returning(frags, total=20, pagina=2)
    uc = ListarFragmentos(repo)

    result = await uc.ejecutar(
        ListarFragmentosRequest(
            pagina=2,
            por_pagina=10,
            norma_id=3,
            tipo_chunk="articulo_simple",
            nivel_jerarquico=4,
            texto="procedimiento",
        )
    )

    repo.list_fragmentos.assert_awaited_once_with(
        pagina=2,
        por_pagina=10,
        norma_id=3,
        tipo_chunk="articulo_simple",
        nivel_jerarquico=4,
        texto="procedimiento",
    )
    assert result.total == 20
    assert result.pagina == 2
    assert len(result.items) == 2
    assert result.items[0].tipo_chunk == "articulo_simple"


@pytest.mark.asyncio
async def test_clamp_por_pagina_maximo() -> None:
    """por_pagina > MAX -> se limita a MAX por la validacion del use case."""
    repo = _repo_returning([], total=0)
    uc = ListarFragmentos(repo)

    await uc.ejecutar(ListarFragmentosRequest(por_pagina=500))

    kwargs = repo.list_fragmentos.await_args.kwargs
    assert kwargs["por_pagina"] == MAX_POR_PAGINA


@pytest.mark.asyncio
async def test_clamp_pagina_minima() -> None:
    """pagina < 1 -> se clampa a 1."""
    repo = _repo_returning([], total=0)
    uc = ListarFragmentos(repo)

    await uc.ejecutar(ListarFragmentosRequest(pagina=0))

    kwargs = repo.list_fragmentos.await_args.kwargs
    assert kwargs["pagina"] == 1
