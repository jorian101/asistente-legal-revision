"""Tests del bus de eventos y tipos de pipeline (Sprint 7)."""

from __future__ import annotations

import asyncio

import pytest

from src.application.observability import (
    FaseCompletada,
    FaseIniciada,
    fase_a_legible,
    get_event_bus,
    resumen_legible_fase,
)


class TestPipelineEvents:
    """Tests de los dataclasses de eventos."""

    def test_fase_iniciada_creacion(self):
        e = FaseIniciada(
            consulta_id=1,
            fase="entendiendo",
            timestamp_ms=1000,
            usuario_id=1,
            usuario_nombre="operador",
            expediente_id=None,
            tipo_respuesta="consulta_simple",
        )
        assert e.consulta_id == 1
        assert e.fase == "entendiendo"
        assert e.usuario_nombre == "operador"

    def test_fase_completada_con_metadata(self):
        e = FaseCompletada(
            consulta_id=1,
            fase="buscando",
            timestamp_ms=1500,
            usuario_id=1,
            usuario_nombre="operador",
            expediente_id=None,
            tipo_respuesta="consulta_simple",
            duracion_ms=300,
            resumen_legible="Buscamos en 12 fragmentos",
            metadata={"fragmentos_encontrados": 12},
        )
        assert e.duracion_ms == 300
        assert e.metadata["fragmentos_encontrados"] == 12

    def test_fase_a_legible(self):
        assert fase_a_legible("entendiendo") == "Entendiendo tu pregunta"
        assert fase_a_legible("buscando") == "Buscando en el corpus jurídico"
        assert fase_a_legible("reordenando") == "Reordenando por relevancia"
        assert fase_a_legible("expandiendo") == "Agregando contexto"
        assert fase_a_legible("generando") == "Generando respuesta"

    def test_resumen_legible_buscar(self):
        resumen = resumen_legible_fase(
            "buscando",
            {"fragmentos_encontrados": 12, "normas_consultadas": ["CPE", "CPPM"]},
        )
        assert "12 fragmentos" in resumen
        assert "CPE" in resumen
        assert "CPPM" in resumen

    def test_resumen_legible_reordenar(self):
        resumen = resumen_legible_fase(
            "reordenando",
            {"modelo": "local", "top_k_final": 7, "fallback": False},
        )
        assert "Reordenamos" in resumen
        assert "local" in resumen
        assert "top 7" in resumen

    def test_resumen_legible_con_fallback(self):
        resumen = resumen_legible_fase(
            "reordenando",
            {"modelo": "local", "top_k_final": 7, "fallback": True},
        )
        assert "fallback" in resumen


class TestEventBus:
    """Tests del bus in-memory."""

    @pytest.mark.asyncio
    async def test_publica_y_recibe(self):

        bus = get_event_bus()
        bus._subscribers.clear()  # limpiar antes

        # Subscribe primero
        recibido = []

        async def consumidor():
            async for e in bus.subscribe():
                recibido.append(e)
                break

        task = asyncio.create_task(consumidor())
        await asyncio.sleep(0.01)  # dar tiempo a que se registre

        evento = FaseIniciada(
            consulta_id=1,
            fase="entendiendo",
            timestamp_ms=1000,
            usuario_id=1,
            usuario_nombre="operador",
            expediente_id=None,
            tipo_respuesta="consulta_simple",
        )

        await bus.publish(evento)

        await asyncio.wait_for(task, timeout=1.0)

        assert len(recibido) == 1
        assert recibido[0].fase == "entendiendo"

    @pytest.mark.asyncio
    async def test_multiples_subscriptores(self):

        bus = get_event_bus()
        bus._subscribers.clear()

        # Subscribe 3 veces
        resultados = [[] for _ in range(3)]
        for i in range(3):

            async def consumidor(idx):
                async for e in bus.subscribe():
                    resultados[idx].append(e)
                    break

            asyncio.create_task(consumidor(i))

        await asyncio.sleep(0.01)

        evento = FaseIniciada(
            consulta_id=2,
            fase="buscando",
            timestamp_ms=2000,
            usuario_id=2,
            usuario_nombre="supervisor",
            expediente_id=5,
            tipo_respuesta="auto_vista_consulta",
        )

        await bus.publish(evento)

        await asyncio.sleep(0.1)

        assert all(len(r) == 1 for r in resultados)
        assert all(r[0].fase == "buscando" for r in resultados)


class TestFaseALegible:
    def test_todas_las_fases(self):
        assert fase_a_legible("entendiendo") == "Entendiendo tu pregunta"
        assert fase_a_legible("buscando") == "Buscando en el corpus jurídico"
        assert fase_a_legible("reordenando") == "Reordenando por relevancia"
        assert fase_a_legible("expandiendo") == "Agregando contexto"
        assert fase_a_legible("generando") == "Generando respuesta"
