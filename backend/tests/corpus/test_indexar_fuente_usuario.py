"""IndexarNorma con fuentes de usuario: categoría explícita, propietario y estado."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest

LEY = "Artículo 1. (Objeto). Regula los recursos.\n\nArtículo 2. (Alcance). Aplica a todos.\n"
AUTO = "VISTOS: el recurso. CONSIDERANDO I: Que, hay competencia. POR TANTO: CONFIRMAR."


def _repo_vectorial():
    repo = MagicMock()
    repo._collection_has_sparse = MagicMock(return_value=False)
    repo.upsert_corpus = AsyncMock()
    return repo


def _uc():
    embedder = MagicMock()
    embedder.embed = AsyncMock(side_effect=lambda textos: [[0.1] * 4 for _ in textos])
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 21
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda f: f)
    repos = {"corpus": _repo_vectorial(), "juris": _repo_vectorial(), "doctrina": _repo_vectorial()}
    uc = IndexarNorma(
        text_extractor=MagicMock(),
        embedder=embedder,
        vector_repo=repos["corpus"],
        norma_repo=norma_repo,
        fragmento_repo=fragmento_repo,
        vector_repo_jurisprudencia=repos["juris"],
        vector_repo_doctrina=repos["doctrina"],
    )
    return uc, norma_repo, repos


@pytest.mark.asyncio
async def test_norma_privada_de_usuario_se_indexa_por_articulos_con_visibilidad():
    uc, norma_repo, repos = _uc()

    resp = await uc.ejecutar(
        IndexarNormaRequest(
            abreviatura="LEY-1234",
            ruta_pdf="/tmp/x.txt",
            texto_directo=LEY,
            categoria="norma",
            nombre="Ley de recursos",
            jerarquia="supletoria",
            propietario_id=10,
            estado_visibilidad="privado",
        )
    )

    norma = norma_repo.save.await_args.args[0]
    assert (norma.nombre, norma.jerarquia, norma.tipo) == (
        "Ley de recursos",
        "supletoria",
        "reglamento",
    )
    assert (norma.propietario_id, norma.estado_visibilidad) == (10, "privado")
    assert resp.qdrant_collection == "corpus_juridico"
    puntos = repos["corpus"].upsert_corpus.await_args.args[0]
    assert len(puntos) == 2
    assert puntos[0]["payload"]["visibilidad"] == "privado"
    assert puntos[0]["payload"]["propietario_id"] == 10
    assert puntos[0]["payload"]["tipo_fuente"] == "norma"


@pytest.mark.asyncio
async def test_sentencia_de_usuario_va_a_la_coleccion_jurisprudencia():
    uc, norma_repo, repos = _uc()

    resp = await uc.ejecutar(
        IndexarNormaRequest(
            abreviatura="JUR-AUTO-1",
            ruta_pdf="/tmp/x.txt",
            texto_directo=AUTO,
            categoria="jurisprudencia",
            tipo="sentencia_cidh",
            estado_visibilidad="pendiente",
            propietario_id=10,
        )
    )

    norma = norma_repo.save.await_args.args[0]
    assert (norma.tipo, norma.jerarquia) == ("sentencia_cidh", "jurisprudencia")
    assert resp.qdrant_collection == "jurisprudencia"
    repos["corpus"].upsert_corpus.assert_not_called()
    payload = repos["juris"].upsert_corpus.await_args.args[0][0]["payload"]
    assert payload["visibilidad"] == "pendiente"


@pytest.mark.asyncio
async def test_libro_de_usuario_va_a_la_coleccion_doctrina():
    uc, norma_repo, repos = _uc()
    texto = "\n".join(f"Línea {i} sobre argumentación jurídica." for i in range(200))

    resp = await uc.ejecutar(
        IndexarNormaRequest(
            abreviatura="LIB-MI-LIBRO",
            ruta_pdf="/tmp/x.txt",
            texto_directo=texto,
            categoria="doctrina",
            nombre="Mi libro",
            propietario_id=10,
            estado_visibilidad="privado",
        )
    )

    assert resp.qdrant_collection == "doctrina"
    assert norma_repo.save.await_args.args[0].tipo == "doctrina_libro"
    repos["doctrina"].upsert_corpus.assert_awaited_once()


@pytest.mark.asyncio
async def test_lo_global_no_lleva_visibilidad_en_el_payload():
    """Compatibilidad: el corpus global sigue sin visibilidad (publico para todos)."""
    uc, _, repos = _uc()

    await uc.ejecutar(
        IndexarNormaRequest(
            abreviatura="LEY-1", ruta_pdf="/tmp/x.txt", texto_directo=LEY, categoria="norma"
        )
    )

    payload = repos["corpus"].upsert_corpus.await_args.args[0][0]["payload"]
    assert "visibilidad" not in payload
    assert "propietario_id" not in payload


@pytest.mark.asyncio
async def test_norma_con_jerarquia_invalida_falla():
    uc, _, _ = _uc()

    with pytest.raises(ValueError, match="(?i)jerarqu"):
        await uc.ejecutar(
            IndexarNormaRequest(
                abreviatura="LEY-2",
                ruta_pdf="/tmp/x.txt",
                texto_directo=LEY,
                categoria="norma",
                jerarquia="doctrina",
            )
        )
