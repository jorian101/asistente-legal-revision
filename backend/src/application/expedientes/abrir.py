"""Interactor: AbrirExpediente — Caso de uso abrir expediente procesal.

Sprint 4 Fase 2. El supervisor abre un expediente (caso procesal TSJM) que
agrupa obras (piezas procesales) y chats.

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados.
Responsabilidades:
1. Validar numero_caso UNIQUE (si ya existe, ValueError).
2. Construir entidad Expediente con estado='activo' por defecto.
3. Persistir via ExpedienteRepo.guardar.
4. Devolver Response con id asignado.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.expediente_repo import ExpedienteRepo
from src.domain.entities.expediente import Expediente


@dataclass(slots=True)
class AbrirExpedienteRequest:
    """Entrada del caso de uso AbrirExpediente."""

    numero_caso: str
    tipo_proceso: str  # 'consulta' | 'apelacion_incidental'
    tribunal_origen: str
    procesado_nombre: str
    delito: str
    abierto_por: int  # usuario_id del JWT (supervisor)
    procesado_grado: str | None = None
    sentencia_origen: str | None = None
    fojas_total: int | None = None


@dataclass(slots=True)
class AbrirExpedienteResponse:
    """Salida del caso de uso AbrirExpediente."""

    expediente_id: int
    numero_caso: str
    estado: str
    creado_at_iso: str  # ISO 8601 str (no datetime para evitar acoplamiento)


class NumeroCasoDuplicadoError(ValueError):
    """El numero_caso ya existe en la BD (UNIQUE constraint)."""


class AbrirExpediente:
    """Caso de uso: Abrir un expediente procesal nuevo."""

    def __init__(self, expediente_repo: ExpedienteRepo) -> None:
        self._expediente_repo = expediente_repo

    async def ejecutar(self, request: AbrirExpedienteRequest) -> AbrirExpedienteResponse:
        """Ejecuta la apertura.

        Raises:
            NumeroCasoDuplicadoError: si ya existe un expediente con ese numero_caso.
            ValueError: si tipo_proceso no es valor permitido (lo valida la entity).
        """
        # 1. Validar numero_caso UNIQUE
        existente = await self._expediente_repo.obtener_por_numero_caso(request.numero_caso)
        if existente is not None:
            raise NumeroCasoDuplicadoError(
                f"Ya existe un expediente con numero_caso '{request.numero_caso}'."
            )

        # 2. Construir entidad Expediente (estado default 'activo').
        expediente = Expediente(
            id=None,
            numero_caso=request.numero_caso,
            tipo_proceso=request.tipo_proceso,
            tribunal_origen=request.tribunal_origen,
            procesado_nombre=request.procesado_nombre,
            procesado_grado=request.procesado_grado,
            delito=request.delito,
            sentencia_origen=request.sentencia_origen,
            fojas_total=request.fojas_total,
            estado="activo",
            abierto_por=request.abierto_por,
        )

        # 3. Persistir
        guardado = await self._expediente_repo.guardar(expediente)

        # 4. Response
        return AbrirExpedienteResponse(
            expediente_id=guardado.id,  # type: ignore[arg-type]
            numero_caso=guardado.numero_caso,
            estado=guardado.estado,
            creado_at_iso=guardado.created_at.isoformat() if guardado.created_at else "",
        )
