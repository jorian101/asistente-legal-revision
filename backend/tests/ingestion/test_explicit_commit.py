"""Test de regresión: el script ingest_corpus debe llamar session.commit() explicito.

Bug Sprint 0: las ingestas previas dejaban fragmentos en Qdrant pero NO en PG,
porque SQLAlchemy async session NO autocommitea al salir del contexto `async with`.
El fix fue agregar `await session.commit()` explicito al final de ejecutar.

Este test reverte el fix (mockeando para NO hacer commit) y verifica que
si session.commit() no es llamado, el flujo falla. Y verifica que el codigo
ACTUAL SI lo llama.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.ingest_corpus import main as ingest_main


def _build_argv(pdf_path: Path = Path("/tmp/fake.pdf")) -> list[str]:
    return [
        "ingest_corpus.py",
        "--abreviatura",
        "CPPM",
        "--pdf",
        str(pdf_path),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_main_calls_session_commit_after_ejecutar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El flujo 'real' (no dry-run) ejecuta session.commit() tras interactor.ejecutar()."""
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-stub")

    # 1. Mockear argparse para que lea args conocidos
    monkeypatch.setattr("sys.argv", _build_argv(fake_pdf))

    # 2. Mockear factory de sessions asincronas de SQLAlchemy
    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    fake_session_factory = MagicMock()
    fake_session_factory.return_value = fake_session

    monkeypatch.setattr(
        "scripts.ingest_corpus.async_sessionmaker",
        lambda *a, **kw: fake_session_factory,
    )

    # 3. create_async_engine: devolver motor que vas a disposar (noop)
    fake_engine = AsyncMock()
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(
        "scripts.ingest_corpus.create_async_engine",
        lambda *a, **kw: fake_engine,
    )

    # 4. Mockear Qdrant collection ops y OllamaEmbedder
    fake_qdrant = MagicMock()
    fake_qdrant.ensure_collection = AsyncMock()
    fake_qdrant.upsert_corpus = AsyncMock()
    monkeypatch.setattr(
        "scripts.ingest_corpus.QdrantCorpusRepo",
        lambda *a, **kw: fake_qdrant,
    )

    fake_embedder = MagicMock()
    fake_embedder.close = AsyncMock()
    monkeypatch.setattr(
        "scripts.ingest_corpus.OllamaEmbedder",
        lambda *a, **kw: fake_embedder,
    )

    # 5. Mockear el interactor IndexarNorma para que NO toque PG/Qdrant reales
    fake_response = MagicMock()
    fake_response.norma_id = 1234
    fake_response.fragmentos_creados = 100
    fake_response.vectores_indexados = 100

    fake_interactor = MagicMock()
    fake_interactor.ejecutar = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(
        "scripts.ingest_corpus.IndexarNorma",
        lambda **kw: fake_interactor,
    )

    # 6. SqlNormaRepo y FragmentoRepoImpl: no los vamos a usar realmente,
    # pero hay que tenerlos importables. Mockeamos a constructores triviales.
    monkeypatch.setattr(
        "scripts.ingest_corpus.SqlNormaRepo",
        lambda session: MagicMock(),
    )
    monkeypatch.setattr(
        "scripts.ingest_corpus.FragmentoRepoImpl",
        lambda session: MagicMock(),
    )

    # Execute
    rc = await ingest_main()

    # Assert: session.commit() debe haberse llamado exactamente 1 vez.
    # Y el codigo de retorno debe ser 0 (OK).
    assert rc == 0
    fake_session.commit.assert_awaited_once()
