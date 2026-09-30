"""Interactor: ListarHistorialExpediente — Listar obras de un expediente.

Sprint 4 Fase 2. Aplica Regla 5 Trail of Bits (BLOQUEANTE): el filtro de
visibilidad vive en el ADAPTER (ObraRepo.listar_por_expediente), este use
case solo pasa `usuario_id`. El usuario ve:
- Sus propias obras (propietario_id == usuario_id)
- Obras publicadas de otros (estado_visibilidad == 'publicado')
- NUNCA obras privadas ajenas.

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.obra_repo import ObraRepo
from src.domain.entities.obra import Obra


@dataclass(slots=True)
class ListarHistorialRequest:
    """Entrada del caso de uso ListarHistorialExpediente."""

    expediente_id: int
    usuario_id: int  # JWT del solicitante
    solo_propias: bool = False  # True: vista "mis obras subidas"


@dataclass(slots=True)
class ObraResumenDTO:
    """Resumen de una obra para lista historial (sin contenido_texto para
    evitar memory heavy en listados largos)."""

    id: int
    expediente_id: int
    propietario_id: int
    tipo_documento: str
    nombre_archivo: str
    estado_visibilidad: str
    estado_procesamiento: str
    es_propia: bool  # True si propietario_id == usuario_id solicitante
    created_at_iso: str
    autor_nombre: str | None = None
    autor_cargo: str | None = None
    autor_instancia: str | None = None
    # Promoción a jurisprudencia: promocion_pendiente | promovida | promocion_rechazada.
    estado_validacion: str | None = None


@dataclass(slots=True)
class ListarHistorialResponse:
    """Salida del caso de uso ListarHistorialExpediente."""

    expediente_id: int
    obras: list[ObraResumenDTO]
    total: int


class ListarHistorialExpediente:
    """Caso de uso: Listar obras de un expediente (Regla 5 aplicada)."""

    def __init__(self, obra_repo: ObraRepo, auth_repo=None) -> None:
        self._obra_repo = obra_repo
        self._auth_repo = auth_repo

    async def ejecutar(self, request: ListarHistorialRequest) -> ListarHistorialResponse:
        """Ejecuta el listado.

        Returns:
            ListarHistorialResponse con obras (DTOs) y total.
            Las obras visibles se determina en el adapter; aquí solo se
            empaqueta el response. El autor se resuelve por propietario
            (nombre + cargo) con cache, o se usa autor_instancia si la obra
            vino de la instancia inferior.
        """
        obras: list[Obra] = await self._obra_repo.listar_por_expediente(
            expediente_id=request.expediente_id,
            usuario_id=request.usuario_id,
            solo_propias=request.solo_propias,
        )
        # Plan C (C1.4): la doctrina/criterio del expediente NO se lista como
        # obra del historial — se muestra solo en el desplegable "Doctrina
        # privada de este expediente" (evita duplicación en el chat).
        obras = [o for o in obras if o.tipo_documento not in ("doctrina", "criterio")]
        total = len(obras)

        # Cache de autores por propietario_id (evita N+1 en listados largos).
        autores: dict[int, tuple[str | None, str | None]] = {}

        async def _autor(propietario_id: int) -> tuple[str | None, str | None]:
            if propietario_id not in autores and self._auth_repo is not None:
                autor = await self._auth_repo.get_by_id(propietario_id)
                autores[propietario_id] = (
                    autor.nombre if autor else None,
                    autor.cargo if autor else None,
                )
            return autores.get(propietario_id, (None, None))

        dtos = []
        for obra in obras:
            nombre, cargo = await _autor(obra.propietario_id)
            dtos.append(
                ObraResumenDTO(
                    id=obra.id,  # type: ignore[arg-type]
                    expediente_id=obra.expediente_id,
                    propietario_id=obra.propietario_id,
                    tipo_documento=obra.tipo_documento,
                    nombre_archivo=obra.nombre_archivo,
                    estado_visibilidad=obra.estado_visibilidad,
                    estado_procesamiento=obra.estado_procesamiento,
                    es_propia=(obra.propietario_id == request.usuario_id),
                    autor_nombre=nombre,
                    autor_cargo=cargo,
                    autor_instancia=obra.autor_instancia,
                    estado_validacion=obra.estado_validacion,
                    created_at_iso=obra.created_at.isoformat() if obra.created_at else "",
                )
            )

        return ListarHistorialResponse(
            expediente_id=request.expediente_id,
            obras=dtos,
            total=total,
        )
