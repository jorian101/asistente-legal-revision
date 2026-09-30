"""Port: ExpedienteRepo — Repositorio de expedientes (tabla `expediente`).

Protocols (structural typing) — las implementaciones no necesitan heredar.

Sprint 4: el supervisor abre expedientes (caso procesal TSJM) que agrupan
obras (piezas procesales) y chats. Elpuerto cubre CRUD básico + listado
por `abierto_por` (quién abrió el expediente).
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.expediente import Expediente


class ExpedienteRepo(Protocol):
    """Repositorio de expedientes (tabla `expediente`)."""

    async def guardar(self, expediente: Expediente) -> Expediente:
        """Crea un expediente. Devuelve entidad con id y created_at asignados."""
        ...

    async def obtener(self, expediente_id: int) -> Expediente | None:
        """Obtiene un expediente por PK. Sin filtro de propietario (es público
        dentro de la app — el ExpedienteModel no tiene propietario_id, lo
        tienen las Obras y los chats). Regla 5 vive en `obra_repo`.
        """
        ...

    async def obtener_por_numero_caso(self, numero_caso: str) -> Expediente | None:
        """Obtiene por UNIQUE numero_caso. None si no existe."""
        ...

    async def listar_por_usuario(
        self,
        usuario_id: int,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        """Lista expedientes abiertos por `usuario_id` (filtro `abierto_por`)."""
        ...

    async def listar_todos(
        self,
        *,
        incluir_archivados: bool = False,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        """Lista expedientes visibles (Plan: expedientes compartidos).

        - Supervisor: `incluir_archivados=True` -> ve todos (activos+archivados).
        - Operador: `incluir_archivados=False` -> ve solo activos.
        Restaura el comportamiento perdido del fix #322 (todos los operadores ven
        los expedientes que el supervisor abre, mientras esten activos).
        """
        ...

    async def actualizar_estado(self, expediente_id: int, estado: str) -> Expediente | None:
        """Cambia estado (activo/archivado). Devuelve actualizado o None."""
        ...

    async def actualizar(
        self,
        expediente_id: int,
        *,
        numero_caso: str | None = None,
        procesado_nombre: str | None = None,
        delito: str | None = None,
        tribunal_origen: str | None = None,
        tipo_proceso: str | None = None,
    ) -> Expediente | None:
        """Actualiza metadatos del expediente."""
        ...
