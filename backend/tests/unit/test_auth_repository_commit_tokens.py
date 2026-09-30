"""Revocar, guardar refresh tokens y registrar intentos deben hacer commit.

`get_db_session` no hace commit al cerrar (AsyncSession no autocommitea) y los casos
de uso tampoco: sin commit explicito la rotacion del refresh token, la revocacion por
replay/logout, el refresh emitido tras el 2FA y los intentos de login se perdian al
cerrar el request (R2). El login solo persistia por el commit del registro de auditoria.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.auth_repository import SqlAuthRepository


def _repo() -> tuple[SqlAuthRepository, AsyncMock]:
    session = AsyncMock()
    session.add = MagicMock()
    return SqlAuthRepository(session), session


@pytest.mark.asyncio
async def test_guardar_refresh_token_hace_commit() -> None:
    repo, session = _repo()

    await repo.guardar_refresh_token(1, "hash", datetime.now(UTC))

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revocar_refresh_token_hace_commit() -> None:
    repo, session = _repo()

    await repo.revocar_refresh_token("hash")

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revocar_todos_los_refresh_tokens_hace_commit() -> None:
    repo, session = _repo()

    await repo.revocar_todos_refresh_tokens(1)

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_registrar_intento_hace_commit() -> None:
    repo, session = _repo()

    await repo.registrar_intento("10702191", "127.0.0.1", exitoso=False)

    session.commit.assert_awaited_once()
