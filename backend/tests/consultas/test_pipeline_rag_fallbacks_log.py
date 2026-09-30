"""Los fallbacks best-effort de PipelineRAG no deben fallar en silencio (F-20)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.application.services.pipeline_rag import PipelineRAG

CFG = SimpleNamespace(top_k_denso=5, top_k_lexico=5)


def _pipeline(buscador: MagicMock) -> PipelineRAG:
    return PipelineRAG(buscador=buscador, reranker_svc=MagicMock(), config_repo=MagicMock())


async def test_fusionar_normas_corpus_loguea_si_falla_la_busqueda(caplog) -> None:
    buscador = MagicMock()
    buscador.buscar = AsyncMock(side_effect=RuntimeError("qdrant caido"))
    candidatos: list = []

    with caplog.at_level("WARNING"):
        await _pipeline(buscador)._fusionar_normas_corpus(
            candidatos, "consulta", "auto_vista_consulta", 7, 1, CFG
        )

    assert candidatos == []
    assert "normas del corpus" in caplog.text


async def test_fallback_obras_loguea_si_falla_la_recuperacion(caplog) -> None:
    frag_repo = MagicMock()
    frag_repo.get_by_expediente = AsyncMock(side_effect=RuntimeError("pg caida"))
    buscador = MagicMock()
    buscador._fragmento_repo = frag_repo
    candidatos: list = []

    with caplog.at_level("WARNING"):
        await _pipeline(buscador)._aplicar_fallback_obras(
            candidatos, "auto_vista_consulta", 7, None, 1
        )

    assert "obrados" in caplog.text
