"""Tests de los UC de soft delete universal (CRITICAL #3).

- eliminar_norma: activo=False (admin)
- eliminar_expediente: estado='archivado'
- eliminar_borrador: activo=False SOLO propietario (Regla 7)

Usa fake repos (sin DB) para probar el contrato.
"""

from __future__ import annotations

import pytest

from src.application.borradores.eliminar_borrador import eliminar_borrador
from src.application.corpus.eliminar_norma import eliminar_norma
from src.application.expedientes.eliminar_expediente import eliminar_expediente
from src.domain.entities.expediente import Expediente


class FakeNormaRepo:
    def __init__(self, activas: set[int]) -> None:
        self.activas = activas

    async def eliminar_soft(self, norma_id: int) -> bool:
        if norma_id in self.activas:
            self.activas.discard(norma_id)
            return True
        return False


class FakeExpedienteRepo:
    def __init__(self, estados: dict[int, str]) -> None:
        self.estados = estados

    async def actualizar_estado(self, expediente_id: int, estado: str) -> Expediente | None:
        if expediente_id not in self.estados:
            return None
        self.estados[expediente_id] = estado
        return Expediente(
            id=expediente_id,
            numero_caso="X",
            tipo_proceso="consulta",
            tribunal_origen="T",
            procesado_nombre="N",
            delito="D",
            abierto_por=1,
            estado=estado,  # type: ignore[arg-type]
        )


class FakeBorradorRepo:
    def __init__(self, propietarios: dict[int, int], activos: set[int]) -> None:
        self.propietarios = propietarios
        self.activos = activos

    async def eliminar_soft(self, borrador_id: int, propietario_id: int) -> bool:
        if (
            borrador_id in self.propietarios
            and self.propietarios[borrador_id] == propietario_id
            and borrador_id in self.activos
        ):
            self.activos.discard(borrador_id)
            return True
        return False


@pytest.mark.asyncio
async def test_eliminar_norma_activa() -> None:
    """Norma activa -> True (activo=False)."""
    repo = FakeNormaRepo({1, 2})
    assert await eliminar_norma(repo, norma_id=1) is True
    assert repo.activas == {2}


@pytest.mark.asyncio
async def test_eliminar_norma_inexistente() -> None:
    """Norma inexistente/ya inactiva -> False."""
    repo = FakeNormaRepo(set())
    assert await eliminar_norma(repo, norma_id=99) is False


@pytest.mark.asyncio
async def test_eliminar_expediente_archiva() -> None:
    """Expediente activo -> estado 'archivado' (True)."""
    repo = FakeExpedienteRepo({1: "activo", 2: "activo"})
    assert await eliminar_expediente(repo, expediente_id=1) is True
    assert repo.estados[1] == "archivado"
    assert repo.estados[2] == "activo"  # el otro no se toca


@pytest.mark.asyncio
async def test_eliminar_expediente_inexistente() -> None:
    """Expediente inexistente -> False."""
    repo = FakeExpedienteRepo({})
    assert await eliminar_expediente(repo, expediente_id=9) is False


@pytest.mark.asyncio
async def test_eliminar_borrador_propietario() -> None:
    """Regla 7: el propietario elimina su borrador."""
    repo = FakeBorradorRepo(propietarios={1: 3, 2: 3}, activos={1, 2})
    assert await eliminar_borrador(repo, borrador_id=1, propietario_id=3) is True
    assert 1 not in repo.activos
    assert 2 in repo.activos  # el otro borrador del mismo propietario queda


@pytest.mark.asyncio
async def test_eliminar_borrador_ajeno() -> None:
    """Regla 7 BLOQUEANTE: usuario 3 no elimina el borrador del usuario 4."""
    repo = FakeBorradorRepo(propietarios={1: 4}, activos={1})
    assert await eliminar_borrador(repo, borrador_id=1, propietario_id=3) is False
    assert 1 in repo.activos  # intacto


@pytest.mark.asyncio
async def test_eliminar_borrador_inexistente() -> None:
    """Borrador inexistente -> False."""
    repo = FakeBorradorRepo(propietarios={}, activos=set())
    assert await eliminar_borrador(repo, borrador_id=99, propietario_id=3) is False
