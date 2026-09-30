"""P1: dos pedidos concurrentes con la cache fría corren la SQL del vocabulario una sola vez."""

import asyncio

from src.adapters.postgres import vocabulario


class _SesionLenta:
    def __init__(self) -> None:
        self.ejecuciones = 0

    async def execute(self, _stmt):
        self.ejecuciones += 1
        await asyncio.sleep(0.05)  # simula la SQL de 8-13 s
        return [("prescripcion",), ("de",)]


async def test_concurrentes_ejecutan_la_sql_una_sola_vez():
    vocabulario.invalidate_vocabulario_cache()
    sesion = _SesionLenta()
    try:
        a, b = await asyncio.gather(
            vocabulario.get_vocabulario(sesion), vocabulario.get_vocabulario(sesion)
        )
    finally:
        vocabulario.invalidate_vocabulario_cache()

    assert sesion.ejecuciones == 1
    assert a is b == frozenset({"prescripcion"})
