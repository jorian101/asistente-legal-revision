"""Casos de uso de edicion de formatos: bloques, orden, configuracion y promocion.

Complementa test_formatos_use_cases.py. Sin DB: el repo es un doble en memoria.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.formatos.actualizar_bloque import ActualizarBloque
from src.application.formatos.actualizar_configuracion import ActualizarConfiguracionFormato
from src.application.formatos.eliminar_bloque import EliminarBloque
from src.application.formatos.obtener_formato import ObtenerFormato
from src.application.formatos.promover_formato import PromoverFormato
from src.application.formatos.reordenar_bloques import ReordenarBloques
from src.domain.entities.formato_documento import FormatoDocumento


def _bloque(page: int, index: int, texto: str) -> dict:
    return {
        "page": page,
        "index": index,
        "texto_plantilla": texto,
        "runs": [{"text": texto, "bold": False}],
    }


def _formato(**cambios) -> FormatoDocumento:
    base = {
        "id": 1,
        "tipo_documento": "auto_vista",
        "slug": "auto_vista-test",
        "autor": "aliaga",
        "engine": "python-docx",
        "meta": {"page": {"width": 21.0}},
        "bloques": [_bloque(1, 0, "A"), _bloque(1, 1, "B"), _bloque(1, 2, "C")],
        "esqueleto": [_bloque(1, 0, "A"), _bloque(1, 1, "B"), _bloque(1, 2, "C")],
        "estado": "borrador",
        "version": 1,
        "hash_fuente": "h",
    }
    base.update(cambios)
    return FormatoDocumento(**base)  # type: ignore[arg-type]


def _repo(formato: FormatoDocumento | None) -> MagicMock:
    repo = MagicMock()
    repo.obtener = AsyncMock(return_value=formato)
    repo.obtener_por_slug = AsyncMock(return_value=formato)
    repo.actualizar = AsyncMock(side_effect=lambda f: f)
    repo.listar = AsyncMock(return_value=([], 0))
    return repo


# ---------- ActualizarBloque: rutas no cubiertas ----------


@pytest.mark.asyncio
async def test_actualizar_bloque_aplica_estilo_en_bloque_y_esqueleto() -> None:
    formato = _formato()

    res = await ActualizarBloque(_repo(formato)).ejecutar(
        1, "p1:i1", {"text": "NUEVO", "bold": True, "italic": True, "align": "right", "note": "n"}
    )

    for lista in (res.bloques, res.esqueleto):
        b = lista[1]
        assert b["texto_plantilla"] == "NUEVO"
        assert b["runs"][0] == {"text": "NUEVO", "bold": True, "italic": True, "overridden": True}
        assert b["align"] == "right" and b["note"] == "n" and b["overridden"] is True
    assert res.bloques[0]["runs"][0]["text"] == "A"  # el resto no se toca
    assert res.version == 2


@pytest.mark.asyncio
async def test_actualizar_bloque_formato_inexistente() -> None:
    with pytest.raises(ValueError, match="no encontrado"):
        await ActualizarBloque(_repo(None)).ejecutar(9, "p1:i0", {"text": "x"})


# ---------- EliminarBloque ----------


@pytest.mark.asyncio
async def test_eliminar_bloque_lo_quita_de_bloques_y_esqueleto_y_versiona() -> None:
    repo = _repo(_formato())

    res = await EliminarBloque(repo).ejecutar(1, "p1:i1")

    assert [b["index"] for b in res.bloques] == [0, 2]
    assert [b["index"] for b in res.esqueleto] == [0, 2]
    assert res.version == 2
    repo.actualizar.assert_awaited_once()


@pytest.mark.asyncio
async def test_eliminar_bloque_sin_esqueleto() -> None:
    res = await EliminarBloque(_repo(_formato(esqueleto=None))).ejecutar(1, "p1:i0")

    assert len(res.bloques) == 2 and res.esqueleto is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block_key,mensaje",
    [("basura", "inválido"), ("p1:i99", "no encontrado"), ("pX:iY", "inválido")],
)
async def test_eliminar_bloque_errores(block_key: str, mensaje: str) -> None:
    repo = _repo(_formato())

    with pytest.raises(ValueError, match=mensaje):
        await EliminarBloque(repo).ejecutar(1, block_key)

    repo.actualizar.assert_not_awaited()  # un error no persiste nada


@pytest.mark.asyncio
async def test_eliminar_bloque_formato_inexistente() -> None:
    with pytest.raises(ValueError, match="Formato 9 no encontrado"):
        await EliminarBloque(_repo(None)).ejecutar(9, "p1:i0")


# ---------- ReordenarBloques ----------


@pytest.mark.asyncio
async def test_reordenar_pone_primero_lo_indicado_y_los_no_mencionados_al_final() -> None:
    res = await ReordenarBloques(_repo(_formato())).ejecutar(1, ["p1:i2", "p1:i0"])

    assert [b["index"] for b in res.bloques] == [2, 0, 1]
    assert [b["index"] for b in res.esqueleto] == [2, 0, 1]
    assert res.version == 2


@pytest.mark.asyncio
async def test_reordenar_sin_esqueleto() -> None:
    res = await ReordenarBloques(_repo(_formato(esqueleto=None))).ejecutar(1, ["p1:i1"])

    assert [b["index"] for b in res.bloques] == [1, 0, 2]
    assert res.esqueleto is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "orden,mensaje",
    [(["p1:i0", "p1:i0"], "duplicada"), (["p1:i9"], "no encontrado")],
)
async def test_reordenar_errores_no_persisten(orden: list[str], mensaje: str) -> None:
    repo = _repo(_formato())

    with pytest.raises(ValueError, match=mensaje):
        await ReordenarBloques(repo).ejecutar(1, orden)

    repo.actualizar.assert_not_awaited()


@pytest.mark.asyncio
async def test_reordenar_formato_inexistente() -> None:
    with pytest.raises(ValueError, match="no encontrado"):
        await ReordenarBloques(_repo(None)).ejecutar(9, [])


# ---------- ActualizarConfiguracionFormato ----------


@pytest.mark.asyncio
async def test_configuracion_hace_merge_parcial_sin_pisar_claves_no_enviadas() -> None:
    formato = _formato(meta={"page": {"width": 21.0, "height": 29.7}, "otra": 1})

    res = await ActualizarConfiguracionFormato(_repo(formato)).ejecutar(
        1, page={"height": 33.0}, base={"font": "Arial"}
    )

    assert res.meta["page"] == {"width": 21.0, "height": 33.0}
    assert res.meta["base"] == {"font": "Arial"}
    assert res.meta["otra"] == 1
    assert res.version == 2


@pytest.mark.asyncio
async def test_configuracion_formato_inexistente() -> None:
    with pytest.raises(ValueError, match="no encontrado"):
        await ActualizarConfiguracionFormato(_repo(None)).ejecutar(9, page={"w": 1})


# ---------- ObtenerFormato por slug y PromoverFormato ----------


@pytest.mark.asyncio
async def test_obtener_por_slug_ok_y_no_encontrado() -> None:
    formato = _formato()

    assert await ObtenerFormato(_repo(formato)).ejecutar_por_slug("auto_vista-test") is formato
    with pytest.raises(ValueError, match="slug 'nada' no encontrado"):
        await ObtenerFormato(_repo(None)).ejecutar_por_slug("nada")


@pytest.mark.asyncio
async def test_promover_devuelve_a_borrador_los_otros_canonicos_del_mismo_tipo() -> None:
    nuevo = _formato(id=1)
    anterior = _formato(id=2, estado="canonico", version=3)
    repo = _repo(nuevo)
    repo.listar = AsyncMock(return_value=([anterior, nuevo], 2))

    res = await PromoverFormato(repo).ejecutar(1)

    assert res.estado == "canonico" and res.version == 2
    assert anterior.estado == "borrador" and anterior.version == 4
    assert repo.actualizar.await_count == 2  # el anterior y el nuevo


@pytest.mark.asyncio
async def test_promover_formato_inexistente() -> None:
    with pytest.raises(ValueError, match="no encontrado"):
        await PromoverFormato(_repo(None)).ejecutar(9)
