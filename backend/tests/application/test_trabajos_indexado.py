"""Registro de trabajos de indexado: estado, cancelacion y limpieza."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from src.application.services.trabajos_indexado import (
    CancelacionNoPermitidaError,
    EstadoJob,
    JobInexistenteError,
    JobYaTerminadoError,
    RegistroTrabajos,
    estado_publico,
)


async def _devuelve(valor):
    return valor


async def _registrar(destino: list[str], valor: str) -> None:
    destino.append(valor)


@pytest.mark.asyncio
async def test_trabajo_completado_expone_el_resultado() -> None:
    @dataclass
    class Resultado:
        norma_id: int

    registro = RegistroTrabajos()
    job = registro.lanzar(
        tipo="norma", usuario_id=1, fabrica=lambda token: _devuelve(Resultado(norma_id=21))
    )

    await job.tarea

    assert job.estado is EstadoJob.COMPLETADO
    assert job.error is None
    assert job.terminado_en is not None
    assert estado_publico(job)["resultado"] == {"norma_id": 21}


@pytest.mark.asyncio
async def test_cancelar_detiene_el_trabajo_y_limpia_en_lifo() -> None:
    registro = RegistroTrabajos()
    limpiezas: list[str] = []

    async def cuerpo(token):
        token.al_cancelar(lambda: _registrar(limpiezas, "primera"))
        token.al_cancelar(lambda: _registrar(limpiezas, "segunda"))
        while not token.cancelado:
            await asyncio.sleep(0)
        token.verificar()

    job = registro.lanzar(tipo="norma", usuario_id=1, fabrica=cuerpo)
    registro.cancelar(job.id, usuario_id=1, es_admin=False)

    await job.tarea

    assert job.estado is EstadoJob.CANCELADO
    assert limpiezas == ["segunda", "primera"]


@pytest.mark.asyncio
async def test_una_limpieza_que_falla_no_frena_a_las_demas() -> None:
    registro = RegistroTrabajos()
    limpiezas: list[str] = []

    async def falla() -> None:
        raise RuntimeError("no se pudo deshacer")

    async def cuerpo(token):
        token.al_cancelar(falla)
        token.al_cancelar(lambda: _registrar(limpiezas, "corrio"))
        while not token.cancelado:
            await asyncio.sleep(0)
        token.verificar()

    job = registro.lanzar(tipo="norma", usuario_id=1, fabrica=cuerpo)
    registro.cancelar(job.id, usuario_id=1, es_admin=False)

    await job.tarea

    assert job.estado is EstadoJob.CANCELADO
    assert limpiezas == ["corrio"]


@pytest.mark.asyncio
async def test_una_excepcion_marca_el_trabajo_como_error() -> None:
    registro = RegistroTrabajos()

    async def cuerpo(token):
        raise ValueError("boom")

    job = registro.lanzar(tipo="norma", usuario_id=1, fabrica=cuerpo)

    await job.tarea

    assert job.estado is EstadoJob.ERROR
    assert "boom" in (job.error or "")


@pytest.mark.asyncio
async def test_solo_el_dueno_o_un_admin_puede_cancelar() -> None:
    registro = RegistroTrabajos()
    arrancar = asyncio.Event()

    async def cuerpo(token):
        await arrancar.wait()
        token.verificar()

    job = registro.lanzar(tipo="norma", usuario_id=7, fabrica=cuerpo)

    with pytest.raises(JobInexistenteError):
        registro.cancelar("inexistente", usuario_id=7, es_admin=False)
    with pytest.raises(CancelacionNoPermitidaError):
        registro.cancelar(job.id, usuario_id=8, es_admin=False)

    arrancar.set()
    registro.cancelar(job.id, usuario_id=8, es_admin=True)
    await job.tarea

    assert job.estado is EstadoJob.CANCELADO
    with pytest.raises(JobYaTerminadoError):
        registro.cancelar(job.id, usuario_id=7, es_admin=False)
