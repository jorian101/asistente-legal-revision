"""El contador de intentos 2FA debe incrementarse en una sola sentencia atómica.

Leer el valor y escribir `+1` (dos sentencias) pierde incrementos cuando llegan
verificaciones concurrentes: una ráfaga en paralelo eludiría el bloqueo a los 3
intentos (R2).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.adapters.postgres.repos.auth_repository import SqlAuthRepository


@pytest.mark.asyncio
async def test_incrementar_intentos_2fa_es_un_solo_update_atomico() -> None:
    session = AsyncMock()
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = 2
    session.execute.return_value = resultado

    intentos = await SqlAuthRepository(session).incrementar_intentos_2fa("10702191")

    assert intentos == 2
    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect())).lower()
    assert sql.startswith("update usuario")
    assert "intentos_codigo=(coalesce(usuario.intentos_codigo" in sql.replace(" ", "")
    assert "returning" in sql
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_incrementar_intentos_2fa_de_carnet_inexistente_devuelve_cero() -> None:
    session = AsyncMock()
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = None
    session.execute.return_value = resultado

    assert await SqlAuthRepository(session).incrementar_intentos_2fa("no-existe") == 0
