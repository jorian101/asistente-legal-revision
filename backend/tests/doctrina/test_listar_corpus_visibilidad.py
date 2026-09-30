"""Los catálogos globales (modales del chat) no muestran fuentes privadas de otros."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.listar_corpus_por_jerarquia import ListarCorpusPorJerarquia


def _n(abrev, estado, propietario=None):
    return SimpleNamespace(
        abreviatura=abrev,
        nombre=abrev,
        tipo="doctrina_libro",
        jerarquia="doctrina",
        activo=True,
        indexado=True,
        estado_visibilidad=estado,
        propietario_id=propietario,
    )


@pytest.mark.asyncio
async def test_el_catalogo_muestra_lo_global_y_lo_propio_no_lo_ajeno():
    repo = MagicMock()
    repo.list_all = AsyncMock(
        return_value=[
            _n("LIB-GLOBAL", "global"),
            _n("LIB-MIO", "privado", propietario=10),
            _n("LIB-AJENO", "privado", propietario=99),
            _n("LIB-PENDIENTE-AJENO", "pendiente", propietario=99),
            _n("LIB-RECHAZADO-MIO", "rechazado", propietario=10),
        ]
    )

    items = await ListarCorpusPorJerarquia(repo).ejecutar("doctrina", usuario_id=10)

    assert [i.abreviatura for i in items] == ["LIB-GLOBAL", "LIB-MIO"]


@pytest.mark.asyncio
async def test_sin_usuario_solo_lo_global():
    repo = MagicMock()
    repo.list_all = AsyncMock(
        return_value=[_n("LIB-GLOBAL", "global"), _n("LIB-MIO", "privado", propietario=10)]
    )

    items = await ListarCorpusPorJerarquia(repo).ejecutar("doctrina")

    assert [i.abreviatura for i in items] == ["LIB-GLOBAL"]
