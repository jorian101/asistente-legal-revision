"""Tests unitarios del use case PublicarBorrador (Sprint 6 Fase 1.1).

Sin DB, sin HTTP. FakeRepo que cumple el Protocol BorradorRepo.

Regla 7 Trail of Bits BLOQUEANTE: el test
`test_borrador_publicado_por_otro_usuario_falla` valida que un usuario
no propietario no puede publicar el borrador de otro. Si esto falla, el
Sprint 6 NO puede avanzar — es el guardián de la propiedad intelectual
del expediente.

Cobertura:
- test_borrador_publicado_por_propietario_ok: el dueño publica exitosamente
- test_borrador_publicado_por_otro_usuario_falla: Regla 7 bloqueante
- test_publicar_borrador_ya_publicado_idempotente: idempotente (no double update)
- test_publicar_borrador_inexistente_falla: 403 (no diferenciar de no propietario)
"""

from __future__ import annotations

from typing import override

import pytest

from src.application.borradores.publicar_borrador import (
    PublicarBorrador,
    PublicarBorradorRequest,
)
from src.domain.entities.borrador import Borrador
from src.domain.exceptions import BorradorNoPropioError, BorradorVacioError
from tests._factories import make_borrador

# ---------- FakeRepo ----------


class FakeBorradorRepo:
    """BorradorRepo in-memory para tests. Cumple el Protocol."""

    def __init__(self, existentes: list[Borrador] | None = None) -> None:
        self._por_id: dict[int, Borrador] = {}
        self._next_id = 1
        for b in existentes or []:
            b.id = self._next_id
            self._por_id[self._next_id] = b
            self._next_id += 1

    @override
    async def obtener_por_id(self, borrador_id: int) -> Borrador | None:
        return self._por_id.get(borrador_id)

    @override
    async def actualizar_estado(
        self,
        borrador_id: int,
        estado: str,
        propietario_id: int,
    ) -> Borrador | None:
        # Regla 7: filtro de propietario en el adapter (aqui el fake).
        # None si no existe OR no es propietario (sin diferenciar).
        borrador = self._por_id.get(borrador_id)
        if borrador is None or borrador.propietario_id != propietario_id:
            return None
        # Idempotente: si ya esta 'publicado', no muta updated_at.
        if borrador.estado == estado:
            return borrador
        borrador.estado = estado
        return borrador


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_borrador_publicado_por_propietario_ok() -> None:
    """El dueno del borrador publica exitosamente."""
    borrador = make_borrador(id=None, propietario_id=1, estado="borrador")
    repo = FakeBorradorRepo(existentes=[borrador])

    uc = PublicarBorrador(repo)
    result = await uc.ejecutar(PublicarBorradorRequest(borrador_id=1, propietario_id=1))

    assert result.borrador_id == 1
    assert result.estado == "publicado"
    # Persistencia (in-memory): el borrador en el repo quedo publicado
    persistido = await repo.obtener_por_id(1)
    assert persistido is not None
    assert persistido.estado == "publicado"


@pytest.mark.asyncio
async def test_borrador_publicado_por_otro_usuario_falla() -> None:
    """REGLA 7 BLOQUEANTE — usuario no propietario no puede publicar.

    Trail of Bits: solo el propietario puede cambiar estado a 'publicado'.
    Si este test falla, el Sprint 6 no puede avanzar.
    """
    borrador = make_borrador(id=None, propietario_id=1, estado="borrador")
    repo = FakeBorradorRepo(existentes=[borrador])

    uc = PublicarBorrador(repo)

    # Usuario 2 intenta publicar el borrador del usuario 1
    with pytest.raises(BorradorNoPropioError):
        await uc.ejecutar(PublicarBorradorRequest(borrador_id=1, propietario_id=2))

    # El borrador sigue en estado 'borrador' (no se publico)
    persistido = await repo.obtener_por_id(1)
    assert persistido is not None
    assert persistido.estado == "borrador"


@pytest.mark.asyncio
async def test_publicar_borrador_ya_publicado_idempotente() -> None:
    """Publicar un borrador ya publicado es idempotente (no falla)."""
    borrador = make_borrador(id=None, propietario_id=1, estado="publicado")
    repo = FakeBorradorRepo(existentes=[borrador])

    uc = PublicarBorrador(repo)
    result = await uc.ejecutar(PublicarBorradorRequest(borrador_id=1, propietario_id=1))

    assert result.estado == "publicado"
    assert result.borrador_id == 1


@pytest.mark.asyncio
async def test_publicar_borrador_inexistente_falla() -> None:
    """Si el borrador no existe, mismo error que no propietario (no info leak)."""
    repo = FakeBorradorRepo()  # vacio

    uc = PublicarBorrador(repo)

    with pytest.raises(BorradorNoPropioError):
        await uc.ejecutar(PublicarBorradorRequest(borrador_id=999, propietario_id=1))


@pytest.mark.asyncio
async def test_publicar_borrador_vacio_falla() -> None:
    """REGLA 7+vacio — BorradorVacioError (FIX R2 codex round 3).

    El borrador se persiste con contenido="" antes del stream LLM. Sin
    esta validacion el propietario podria publicar un borrador vacio (ej:
    si cancelo el stream antes de recibir tokens).
    """
    # Borrador existente, del propietario, pero contenido vacio.
    borrador_vacio = make_borrador(id=None, propietario_id=1, contenido="")
    repo = FakeBorradorRepo(existentes=[borrador_vacio])

    uc = PublicarBorrador(repo)

    with pytest.raises(BorradorVacioError):
        await uc.ejecutar(PublicarBorradorRequest(borrador_id=1, propietario_id=1))

    persistido = await repo.obtener_por_id(1)
    assert persistido is not None
    assert persistido.estado == "borrador"  # no se publicó


@pytest.mark.asyncio
async def test_publicar_borrador_solo_espacios_falla() -> None:
    """FIX R2 codex round 3 — strip(): contenido solo espacios tambien rechaza."""
    borrador_espacios = make_borrador(id=None, propietario_id=1, contenido="   \n\n  ")
    repo = FakeBorradorRepo(existentes=[borrador_espacios])

    uc = PublicarBorrador(repo)

    with pytest.raises(BorradorVacioError):
        await uc.ejecutar(PublicarBorradorRequest(borrador_id=1, propietario_id=1))
