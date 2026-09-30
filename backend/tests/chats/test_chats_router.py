"""Tests HTTP del router /chats — creación de chats generales (F0).

TDD con TestClient + dependency_overrides. Sin DB.

Cobertura:
- POST /chats/ sin expediente_id → 201 chat general (expediente_id=None)
- POST /chats/ con expediente inexistente → 404 (comportamiento preservado)
- POST /chats/ con expediente válido → 201 atado al expediente
"""

from __future__ import annotations

from typing import override

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.chat_privado import ChatPrivado
from src.domain.entities.expediente import Expediente
from src.domain.entities.usuario import Usuario
from src.main import app as fastapi_app
from tests._factories import make_usuario


class _FakeChatRepo:
    """ChatRepo in-memory con la firma del port."""

    def __init__(self) -> None:
        self._por_id: dict[int, ChatPrivado] = {}
        self._next_id = 1

    async def guardar(self, chat: ChatPrivado) -> ChatPrivado:
        from datetime import UTC, datetime

        chat.id = self._next_id
        chat.created_at = datetime.now(UTC)
        self._por_id[chat.id] = chat
        self._next_id += 1
        return chat

    async def obtener(self, chat_id: int, propietario_id: int) -> ChatPrivado | None:
        chat = self._por_id.get(chat_id)
        if chat is None or chat.propietario_id != propietario_id:
            return None
        return chat

    async def listar_por_usuario(
        self,
        usuario_id: int,
        expediente_id: int | None = None,
        estado: str | None = None,
    ) -> list[ChatPrivado]:
        items = [c for c in self._por_id.values() if c.propietario_id == usuario_id]
        if expediente_id is not None:
            items = [c for c in items if c.expediente_id == expediente_id]
        if estado is not None:
            items = [c for c in items if c.estado == estado]
        return items

    @override
    async def actualizar_estado(
        self, chat_id: int, propietario_id: int, estado: str
    ) -> ChatPrivado | None:
        chat = await self.obtener(chat_id, propietario_id)
        if chat is None:
            return None
        chat.estado = estado
        return chat

    @override
    async def actualizar_ultimo_mensaje_at(
        self, chat_id: int, propietario_id: int
    ) -> ChatPrivado | None:
        from datetime import UTC, datetime

        chat = await self.obtener(chat_id, propietario_id)
        if chat is None:
            return None
        chat.ultimo_mensaje_at = datetime.now(UTC)
        return chat


class _FakeExpedienteRepoSoloObtener:
    def __init__(self, existentes: list[Expediente] | None = None) -> None:
        self._por_id: dict[int, Expediente] = {}
        for e in existentes or []:
            e.id = len(self._por_id) + 1
            self._por_id[e.id] = e

    async def obtener(self, expediente_id: int) -> Expediente | None:
        return self._por_id.get(expediente_id)


@pytest.fixture
def usuario() -> Usuario:
    return make_usuario(id=3)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


class TestCrearChatGeneral:
    def test_201_chat_sin_expediente(self, client, usuario):
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
        chat_repo = _FakeChatRepo()
        fastapi_app.dependency_overrides[deps.get_chat_repo_dep] = lambda: chat_repo
        fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: (
            _FakeExpedienteRepoSoloObtener()
        )

        resp = client.post("/chats/", json={"titulo": "Consulta doctrina general"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["chat"]["expediente_id"] is None
        assert body["chat"]["titulo"] == "Consulta doctrina general"

    def test_404_expediente_inexistente_se_preserva(self, client, usuario):
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
        fastapi_app.dependency_overrides[deps.get_chat_repo_dep] = lambda: _FakeChatRepo()
        fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: (
            _FakeExpedienteRepoSoloObtener()
        )

        resp = client.post("/chats/", json={"titulo": "X", "expediente_id": 999})

        assert resp.status_code == 404

    def test_201_chat_con_expediente_valido(self, client, usuario):
        exp = Expediente(
            id=None,
            numero_caso="EXP-1",
            procesado_nombre="Perez",
            delito="abandono",
            tribunal_origen="TPJM",
            tipo_proceso="consulta",
            abierto_por=usuario.id,
        )
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
        fastapi_app.dependency_overrides[deps.get_chat_repo_dep] = lambda: _FakeChatRepo()
        repo_exp = _FakeExpedienteRepoSoloObtener([exp])
        fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: repo_exp

        resp = client.post("/chats/", json={"titulo": "Caso Perez", "expediente_id": 1})

        assert resp.status_code == 201
        assert resp.json()["chat"]["expediente_id"] == 1


# ----- F3: caja de cristal (GET /chats/{id}/contexto) -----


class _FakeMensajeRepo:
    def __init__(self, chats: dict[int, list]) -> None:
        self._chats = chats

    async def listar_por_chat(self, chat_id, usuario_id, pagina=1, por_pagina=50):

        items = [m for m in self._chats.get(chat_id, []) if m.usuario_id == usuario_id]
        return items, len(items)


async def test_contexto_chat_devuelve_memoria(client, usuario):

    from src.adapters.http.dependencies_borradores import get_borrador_repo_dep
    from src.domain.entities.mensaje_chat import MensajeChat

    chat_repo = _FakeChatRepo()
    await chat_repo.guardar(
        ChatPrivado(
            id=None,
            expediente_id=None,
            propietario_id=usuario.id,
            titulo="General",
        )
    )
    mensajes = [
        MensajeChat(
            id=1,
            chat_id=1,
            usuario_id=usuario.id,
            tipo="user",
            contenido="que dice el art 184",
            razonamiento="",
            estado="activo",
            posicion=1,
            metadatos={},
        ),
        MensajeChat(
            id=2,
            chat_id=1,
            usuario_id=usuario.id,
            tipo="bot",
            contenido="CPPM art 184",
            razonamiento="",
            estado="activo",
            posicion=2,
            metadatos={},
        ),
    ]

    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    fastapi_app.dependency_overrides[deps.get_chat_repo_dep] = lambda: chat_repo
    fastapi_app.dependency_overrides[deps.get_mensaje_chat_repo_dep] = lambda: _FakeMensajeRepo(
        {1: mensajes}
    )
    fastapi_app.dependency_overrides[get_borrador_repo_dep] = lambda: type("B", (), {})()

    resp = client.get("/chats/1/contexto")

    assert resp.status_code == 200
    body = resp.json()
    assert body["turnos_incluidos"] == 2
    assert "art 184" in body["texto"]


async def test_contexto_chat_404_de_ajeno(client, usuario):
    from src.adapters.http.dependencies_borradores import get_borrador_repo_dep

    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    fastapi_app.dependency_overrides[deps.get_chat_repo_dep] = lambda: _FakeChatRepo()
    fastapi_app.dependency_overrides[deps.get_mensaje_chat_repo_dep] = lambda: _FakeMensajeRepo({})
    fastapi_app.dependency_overrides[get_borrador_repo_dep] = lambda: type("B", (), {})()

    resp = client.get("/chats/999/contexto")
    assert resp.status_code == 404
