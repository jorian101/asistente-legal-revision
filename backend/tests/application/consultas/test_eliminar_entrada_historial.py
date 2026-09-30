"""Tests de EliminarEntradaHistorial (CRITICAL #4 — soft delete).

Regla 4 BLOQUEANTE: solo el propietario elimina SU historial. El UC
delega en repo.eliminar_soft que filtra por usuario_id.
"""

from __future__ import annotations

import pytest

from src.application.consultas.eliminar_entrada_historial import (
    eliminar_entrada_historial,
)


class FakeHistorialRepo:
    """ConsultaHistorialRepo in-memory con soft delete."""

    def __init__(self, entradas: list[dict]) -> None:
        self._entradas = entradas  # dicts: {id, usuario_id, activo}

    async def eliminar_soft(self, historial_id: int, usuario_id: int) -> bool:
        for e in self._entradas:
            if e["id"] == historial_id and e["usuario_id"] == usuario_id and e["activo"]:
                e["activo"] = False
                return True
        return False

    async def guardar(self, historial):
        return historial

    async def listar_por_usuario(self, usuario_id, expediente_id, pagina, por_pagina):
        return [], 0

    async def listar_todas(self, pagina, por_pagina):
        return [], 0

    async def actualizar_respuesta(self, historial_id, respuesta, modelo_llm):
        return None


@pytest.mark.asyncio
async def test_elimina_entrada_propia() -> None:
    """Regla 4: el propietario elimina su entrada (activo=False)."""
    repo = FakeHistorialRepo(
        [
            {"id": 1, "usuario_id": 3, "activo": True},
            {"id": 2, "usuario_id": 3, "activo": True},
        ]
    )

    resultado = await eliminar_entrada_historial(repo, historial_id=1, usuario_id=3)

    assert resultado is True
    assert repo._entradas[0]["activo"] is False
    assert repo._entradas[1]["activo"] is True  # la otra no se toca


@pytest.mark.asyncio
async def test_no_elimina_entrada_de_otro_usuario() -> None:
    """Regla 4 BLOQUEANTE: usuario 3 NO elimina la entrada del usuario 4."""
    repo = FakeHistorialRepo(
        [
            {"id": 1, "usuario_id": 4, "activo": True},
        ]
    )

    resultado = await eliminar_entrada_historial(repo, historial_id=1, usuario_id=3)

    assert resultado is False
    assert repo._entradas[0]["activo"] is True  # intacta


@pytest.mark.asyncio
async def test_no_elimina_entrada_inexistente() -> None:
    """ID inexistente -> False (no raise)."""
    repo = FakeHistorialRepo([])

    resultado = await eliminar_entrada_historial(repo, historial_id=999, usuario_id=3)

    assert resultado is False


@pytest.mark.asyncio
async def test_no_reelimina_entrada_ya_inactiva() -> None:
    """Entrada ya eliminada (activo=False) -> False (idempotente)."""
    repo = FakeHistorialRepo(
        [
            {"id": 1, "usuario_id": 3, "activo": False},
        ]
    )

    resultado = await eliminar_entrada_historial(repo, historial_id=1, usuario_id=3)

    assert resultado is False
