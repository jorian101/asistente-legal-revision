"""Dos mensajes concurrentes al mismo chat no pueden compartir posicion.

El indice unico parcial `mensaje_chat_posicion_unico_visibles` rechazaba el segundo
INSERT (500 y mensaje perdido); ni un reintento lo evita bajo contencion (con 15 envios
en paralelo, 9 fallaban). `guardar` serializa por chat con un bloqueo de fila
(`SELECT ... FOR UPDATE` sobre chat_privado) y calcula la posicion dentro del bloqueo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.adapters.postgres.repos.mensaje_chat_repo import MensajeChatRepoImpl
from src.domain.entities.mensaje_chat import MensajeChat


def _mensaje(posicion: int) -> MensajeChat:
    return MensajeChat(
        id=None,
        chat_id=7,
        usuario_id=3,
        tipo="user",
        contenido="hola",
        razonamiento="",
        estado="activo",
        posicion=posicion,
        metadatos=None,
    )


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


@pytest.mark.asyncio
async def test_guardar_bloquea_el_chat_y_calcula_la_posicion_dentro_del_bloqueo() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    bloqueo = MagicMock()
    maximo = MagicMock()
    maximo.scalar.return_value = 4  # otro request ya ocupo hasta la posicion 4
    session.execute.side_effect = [bloqueo, maximo]

    guardado = await MensajeChatRepoImpl(session).guardar(_mensaje(posicion=0))

    assert guardado.posicion == 5
    primera = session.execute.await_args_list[0].args[0]
    assert "for update" in _sql(primera)
    assert "chat_privado" in _sql(primera)
    session.commit.assert_awaited_once()
