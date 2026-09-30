"""Tests de casos de uso del módulo formatos (RG3: commit explícito + visibilidad).

Foca en la lógica de dominio: ActualizarBloque debe validar block_key,
actualizar el bloque correcto y versionar. Listar/Obtener delegan al repo.
Sin DB live — mocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.formatos.actualizar_bloque import ActualizarBloque
from src.application.formatos.listar_formatos import ListarFormatos
from src.application.formatos.obtener_formato import ObtenerFormato
from src.application.formatos.promover_formato import PromoverFormato
from src.domain.entities.formato_documento import FormatoDocumento


def _make_formato(**overrides) -> FormatoDocumento:
    base = {
        "id": 1,
        "tipo_documento": "auto_vista",
        "slug": "auto_vista-test",
        "autor": "aliaga",
        "engine": "python-docx",
        "meta": {"page": {}},
        "bloques": [
            {
                "page": 1,
                "index": 0,
                "align": "center",
                "runs": [{"text": "TRIBUNAL", "bold": True}],
            },
            {
                "page": 1,
                "index": 1,
                "align": "left",
                "runs": [{"text": "Texto original", "bold": False}],
            },
        ],
        "estado": "borrador",
        "version": 1,
        "hash_fuente": "abc123",
    }
    base.update(overrides)
    return FormatoDocumento(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_actualizar_bloque_corrige_texto_y_versiona() -> None:
    formato = _make_formato()
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=formato)
    repo.actualizar = AsyncMock(side_effect=lambda f: f)

    uc = ActualizarBloque(repo)
    result = await uc.ejecutar(1, "p1:i1", {"text": "Texto corregido"})

    assert result.bloques[1]["runs"][0]["text"] == "Texto corregido"
    assert result.bloques[1]["runs"][0]["overridden"] is True
    assert result.version == 2
    repo.actualizar.assert_awaited_once()


@pytest.mark.asyncio
async def test_actualizar_bloque_block_key_invalido_raise() -> None:
    formato = _make_formato()
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=formato)

    uc = ActualizarBloque(repo)
    with pytest.raises(ValueError, match="block_key inválido"):
        await uc.ejecutar(1, "invalido", {"text": "x"})


@pytest.mark.asyncio
async def test_actualizar_bloque_no_encontrado_raise() -> None:
    formato = _make_formato()
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=formato)

    uc = ActualizarBloque(repo)
    with pytest.raises(ValueError, match="no encontrado"):
        await uc.ejecutar(1, "p9:i9", {"text": "x"})


@pytest.mark.asyncio
async def test_listar_formatos_delega_al_repo() -> None:
    repo = MagicMock()
    repo.listar = AsyncMock(return_value=([], 0))
    uc = ListarFormatos(repo)
    items, total = await uc.ejecutar(tipo_documento="auto_vista")
    assert total == 0
    repo.listar.assert_awaited_once()


@pytest.mark.asyncio
async def test_obtener_por_id_no_encontrado_raise() -> None:
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=None)
    uc = ObtenerFormato(repo)
    with pytest.raises(ValueError, match="no encontrado"):
        await uc.ejecutar_por_id(99)


@pytest.mark.asyncio
async def test_promover_cambia_estado_y_versiona() -> None:
    formato = _make_formato(estado="borrador", version=1)
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=formato)
    repo.listar = AsyncMock(return_value=([], 0))
    repo.actualizar = AsyncMock(side_effect=lambda f: f)

    uc = PromoverFormato(repo)
    result = await uc.ejecutar(1)

    assert result.estado == "canonico"
    assert result.version == 2
