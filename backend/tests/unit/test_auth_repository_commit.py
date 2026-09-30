"""Regresión: actualizar_usuario debe hacer commit explícito.

Bug real detectado en E2E: reset-password devolvía 200 pero el hash no
cambiaba en BD porque `actualizar_usuario` ejecutaba el UPDATE sin
`session.commit()`. El UPDATE quedaba en la transacción y se perdía al
cerrar el request.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.auth_repository import SqlAuthRepository
from src.domain.entities.usuario import Usuario


def _make_session() -> tuple[AsyncMock, MagicMock]:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = 42
    session.execute.return_value = result
    session.commit = AsyncMock()
    return session, result


def _make_usuario() -> Usuario:
    return Usuario(
        id=42,
        nombre="Operador",
        carnet="10702191",
        password_hash="nuevo_hash",
        rol="operador_juridico",
        activo=True,
        cargo="Fiscal",
    )


@pytest.mark.asyncio
async def test_actualizar_usuario_hace_commit_explicito() -> None:
    session, _ = _make_session()
    repo = SqlAuthRepository(session)

    await repo.actualizar_usuario(_make_usuario())

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
