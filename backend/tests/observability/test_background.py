"""Las publicaciones de eventos en segundo plano no se pierden ni fallan en silencio (F-20)."""

from __future__ import annotations

import asyncio

from src.application.observability import background
from src.application.observability.background import (
    nuevo_consulta_id,
    publicar_en_segundo_plano,
)


class _BusLento:
    def __init__(self) -> None:
        self.liberar = asyncio.Event()
        self.publicados: list[object] = []

    async def publish(self, evento: object) -> None:
        await self.liberar.wait()
        self.publicados.append(evento)


class _BusRoto:
    async def publish(self, evento: object) -> None:
        raise RuntimeError("bus caido")


async def test_mantiene_una_referencia_fuerte_hasta_terminar() -> None:
    bus = _BusLento()

    tarea = publicar_en_segundo_plano(bus, "evento")  # type: ignore[arg-type]

    assert tarea in background._TAREAS  # sin referencia, el GC podria recolectarla
    bus.liberar.set()
    await tarea
    await asyncio.sleep(0)  # deja correr el done-callback
    assert tarea not in background._TAREAS
    assert bus.publicados == ["evento"]


async def test_un_publish_que_falla_deja_log(caplog) -> None:
    with caplog.at_level("ERROR"):
        tarea = publicar_en_segundo_plano(_BusRoto(), "evento")  # type: ignore[arg-type]
        await asyncio.gather(tarea, return_exceptions=True)
        await asyncio.sleep(0)

    assert "publicar el evento" in caplog.text


def test_consulta_id_es_positivo_de_31_bits_y_no_se_repite() -> None:
    ids = {nuevo_consulta_id() for _ in range(200)}

    assert all(0 <= i < 2**31 for i in ids)
    assert len(ids) == 200
