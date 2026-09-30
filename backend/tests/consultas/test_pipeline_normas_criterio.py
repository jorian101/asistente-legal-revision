"""Las normas que cita el criterio del vocal también se recuperan (verificables).

El criterio se inyecta al prompt y el modelo cita sus normas; sin recuperarlas,
esas citas no constan en ningún segmento. El pipeline las anexa fuera del corte.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.pipeline_rag import PipelineRAG
from src.application.services.reranker_service import RerankerService
from tests._factories import make_fragmento


def _pipeline(*, rerankeados, criterio: str | None, articulos):
    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=list(rerankeados))
    buscador._fragmento_repo = SimpleNamespace(get_articulos=AsyncMock(return_value=articulos))
    reranker = MagicMock(spec=RerankerService)
    reranker.aplicar = AsyncMock(return_value=rerankeados)
    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(top_k_denso=10, top_k_lexico=5, top_k_final=15)
    )
    obra_repo = None
    if criterio is not None:
        obra_repo = SimpleNamespace(
            listar_criterios=AsyncMock(return_value=[SimpleNamespace(contenido_texto=criterio)])
        )
    return PipelineRAG(
        buscador=buscador, reranker_svc=reranker, config_repo=config_repo, obra_repo=obra_repo
    ), buscador


@pytest.mark.asyncio
async def test_normas_del_criterio_se_anexan_al_final() -> None:
    top = make_fragmento(qdrant_point_id="top")
    cpe_179 = make_fragmento(qdrant_point_id="cpe-179")
    pipeline, buscador = _pipeline(
        rerankeados=[(top, 0.9)], criterio="**Art. 179.I CPE**: unidad", articulos=[cpe_179]
    )

    out = await pipeline.ejecutar(consulta="plazo", usuario_id=1, expediente_id=None)

    assert [f.qdrant_point_id for f in out.fragmentos] == ["top", "cpe-179"]
    buscador._fragmento_repo.get_articulos.assert_awaited_once_with([("CPE", 179)])


@pytest.mark.asyncio
async def test_norma_del_criterio_ya_recuperada_no_se_duplica() -> None:
    cpe_179 = make_fragmento(qdrant_point_id="cpe-179")
    pipeline, _ = _pipeline(
        rerankeados=[(cpe_179, 0.9)], criterio="Art. 179.I CPE", articulos=[cpe_179]
    )

    out = await pipeline.ejecutar(consulta="plazo", usuario_id=1, expediente_id=None)

    assert [f.qdrant_point_id for f in out.fragmentos] == ["cpe-179"]


@pytest.mark.asyncio
async def test_sin_criterio_no_anexa_nada() -> None:
    top = make_fragmento(qdrant_point_id="top")
    pipeline, buscador = _pipeline(rerankeados=[(top, 0.9)], criterio=None, articulos=[])

    out = await pipeline.ejecutar(consulta="plazo", usuario_id=1, expediente_id=None)

    assert [f.qdrant_point_id for f in out.fragmentos] == ["top"]
    buscador._fragmento_repo.get_articulos.assert_not_awaited()
