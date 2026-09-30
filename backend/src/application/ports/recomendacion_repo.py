"""Port: RecomendacionRepo — Repositorio de recomendaciones de doctrina.

Protocol (structural typing). Las implementaciones no necesitan heredar.

Operaciones:
- recomendar: crea/actualiza una recomendación (upsert por par único).
- listar_por_expediente: recomendaciones aprobadas de un expediente.
- listar_pendientes: pendientes de aprobación (supervisor).
- aprobar / rechazar: cambia estado (supervisor).
- listar_pendientes_agrupadas: para el "Aprobar todo" del supervisor.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.recomendacion_doctrina import RecomendacionDoctrina


class RecomendacionRepo(Protocol):
    async def recomendar(
        self,
        *,
        obra_global_id: int | None,
        expediente_id: int,
        recomendado_por: int,
        estado: str,
        corpus: str | None = None,
        corpus_ref: str | None = None,
    ) -> RecomendacionDoctrina:
        """Crea una recomendación (o actualiza si el par único ya existe).

        Por obra (obra_global_id) o por corpus N2/N3 (corpus+corpus_ref =
        abreviatura norma). Exactamente una variante no nula.
        """
        ...

    async def listar_por_expediente(
        self,
        expediente_id: int,
        *,
        solo_aprobadas: bool = True,
    ) -> list[RecomendacionDoctrina]:
        """Lista recomendaciones de un expediente."""
        ...

    async def listar_pendientes(
        self,
        *,
        filtro: str | None = None,
    ) -> list[RecomendacionDoctrina]:
        """Lista recomendaciones pendientes de aprobación (supervisor).

        filtro: 'todas' (default) | 'global_pendiente' | 'global_ya_recomendada'.
        """
        ...

    async def aprobar(
        self,
        recomendacion_id: int,
        aprobado_por: int,
    ) -> RecomendacionDoctrina | None:
        """Aprueba una recomendación ('pendiente' -> 'recomendada')."""
        ...

    async def rechazar(
        self,
        recomendacion_id: int,
        aprobado_por: int,
        motivo: str,
    ) -> RecomendacionDoctrina | None:
        """Rechaza una recomendación ('pendiente' -> 'rechazada')."""
        ...

    async def aprobar_todas(
        self,
        aprobado_por: int,
        *,
        ids: list[int] | None = None,
    ) -> int:
        """Aprueba en lote las recomendaciones pendientes (Aprobar todo).

        ids: si se pasa, aprueba solo esas (Seleccionar). Si None, aprueba
        todas las pendientes (Seleccionar todo).
        """
        ...
