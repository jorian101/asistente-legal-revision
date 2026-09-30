"""Cancelacion del indexado: se corta y se deshace lo que alcanzo a escribir."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.services.trabajos_indexado import (
    EstadoJob,
    IndexadoCanceladoError,
    RegistroTrabajos,
    TokenCancelacion,
)

LEY = "Artículo 1. (Objeto). Regula los recursos.\n\nArtículo 2. (Alcance). Aplica a todos.\n"


def _request() -> IndexarNormaRequest:
    return IndexarNormaRequest(
        abreviatura="LEY-1234",
        ruta_pdf="/tmp/x.txt",
        texto_directo=LEY,
        categoria="norma",
        nombre="Ley de recursos",
        jerarquia="supletoria",
    )


def _uc(*, al_embeber=None):
    """IndexarNorma con fakes. `al_embeber` corre justo antes de devolver vectores."""
    embedder = MagicMock()

    async def _embed(textos):
        if al_embeber is not None:
            await al_embeber()
        return [[0.1] * 4 for _ in textos]

    embedder.embed = AsyncMock(side_effect=_embed)

    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 21
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    norma_repo.eliminar_soft = AsyncMock()

    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda f: f)
    fragmento_repo.delete_by_norma = AsyncMock(return_value=2)

    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=False)
    vector_repo.upsert_corpus = AsyncMock()

    uc = IndexarNorma(
        text_extractor=MagicMock(),
        embedder=embedder,
        vector_repo=vector_repo,
        norma_repo=norma_repo,
        fragmento_repo=fragmento_repo,
        vector_repo_jurisprudencia=vector_repo,
        vector_repo_doctrina=vector_repo,
    )
    return uc, norma_repo, fragmento_repo, vector_repo


@pytest.mark.asyncio
async def test_sin_token_indexa_normal():
    uc, norma_repo, _fragmento_repo, vector_repo = _uc()

    resp = await uc.ejecutar(_request())

    assert resp.norma_id == 21
    assert resp.fragmentos_creados == 2
    norma_repo.marcar_indexada.assert_awaited_with(21, None)
    vector_repo.upsert_corpus.assert_awaited()


@pytest.mark.asyncio
async def test_cancelado_antes_de_escribir_no_deja_nada():
    uc, norma_repo, fragmento_repo, vector_repo = _uc()
    token = TokenCancelacion()
    token.cancelar()

    with pytest.raises(IndexadoCanceladoError):
        await uc.ejecutar(_request(), token=token)

    norma_repo.save.assert_not_awaited()
    fragmento_repo.save_many.assert_not_awaited()
    vector_repo.upsert_corpus.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelado_despues_de_escribir_deshace_la_norma():
    """El corte llega en el ultimo punto de control, antes de Qdrant.

    La limpieza la ejecuta el registro al cerrar el trabajo cancelado.
    """
    registro = RegistroTrabajos()
    holder: dict[str, TokenCancelacion] = {}

    async def cancelar() -> None:
        holder["token"].cancelar()

    uc, norma_repo, fragmento_repo, vector_repo = _uc(al_embeber=cancelar)

    def fabrica(token: TokenCancelacion):
        holder["token"] = token
        return uc.ejecutar(_request(), token=token)

    job = registro.lanzar(tipo="norma", usuario_id=1, fabrica=fabrica)
    await job.tarea

    assert job.estado is EstadoJob.CANCELADO
    # Escribio la norma y sus fragmentos, y los deshizo al cancelarse.
    norma_repo.save.assert_awaited()
    fragmento_repo.save_many.assert_awaited()
    fragmento_repo.delete_by_norma.assert_awaited_with(21)
    norma_repo.eliminar_soft.assert_awaited_with(21)
    # Nunca llego a Qdrant ni marco la norma como indexada.
    vector_repo.upsert_corpus.assert_not_awaited()
    norma_repo.marcar_indexada.assert_not_awaited()
