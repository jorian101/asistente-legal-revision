"""Tests: ListarBorradores + ObtenerBorrador use cases.

Sprint 6 Fase 3.2. Cover:
- Listar filtra por propietario (delega al repo)
- Obtener de un borrador ajeno no publicado -> BorradorNoPropioError (403)
- Obtener de un borrador publicado ajeno -> OK (cualquiera lo ve)
- Obtener de un borrador inexistente -> ValueError (404)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.borradores.listar_borradores import ListarBorradores
from src.application.borradores.obtener_borrador import ObtenerBorrador
from src.domain.exceptions import BorradorNoPropioError
from tests._factories import make_borrador


@pytest.mark.asyncio
async def test_listar_filtra_por_propietario():
    """ListarBorradores delega a repo.listar_por_expediente con usuario_id."""
    items = [make_borrador(id=1), make_borrador(id=2)]
    repo = MagicMock()
    repo.listar_por_expediente = AsyncMock(return_value=items)

    uc = ListarBorradores(repo)
    result = await uc.ejecutar(expediente_id=7, usuario_id=10)

    assert result == items
    repo.listar_por_expediente.assert_awaited_once_with(7, 10)


@pytest.mark.asyncio
async def test_obtener_borrador_ajeno_no_publicado_falla():
    """Borrador en estado 'borrador' que no es del usuario -> BorradorNoPropioError."""
    borrador_ajeno = make_borrador(id=5, propietario_id=99, estado="borrador")
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador_ajeno)

    uc = ObtenerBorrador(repo)
    with pytest.raises(BorradorNoPropioError):
        await uc.ejecutar(borrador_id=5, usuario_id=1)


@pytest.mark.asyncio
async def test_obtener_borrador_publicado_ajeno_ok():
    """Borrador publicado lo ve cualquiera (no raise)."""
    publicado_ajeno = make_borrador(id=8, propietario_id=99, estado="publicado")
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=publicado_ajeno)

    uc = ObtenerBorrador(repo)
    result = await uc.ejecutar(borrador_id=8, usuario_id=1)

    assert result.id == 8


@pytest.mark.asyncio
async def test_obtener_borrador_inexistente_raise_value_error():
    """Borrador no encontrado -> ValueError (router mapea a 404)."""
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=None)

    uc = ObtenerBorrador(repo)
    with pytest.raises(ValueError, match="no encontrado"):
        await uc.ejecutar(borrador_id=999, usuario_id=1)
