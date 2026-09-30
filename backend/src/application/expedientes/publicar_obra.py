"""Interactor: PublicarObra — Caso de uso publicar obra (visibilidad).

Sprint 4 Fase 2. Cambia estado_visibilidad 'privado' -> 'publicado'.

Regla 5 Trail of Bits (BLOQUEANTE): el filtro de propietario vive en el
ADAPTER (ObraRepo.publicar valida propietario_id). Este use case solo
pasa `usuario_id` (JWT). Si el caller no es propietario, el adapter
devuelve None y este use case levanta ObraNoPropiaError (403 en router).

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.obra_repo import ObraRepo
from src.application.services.visibilidad_vectorial import sincronizar_visibilidad_vectorial


@dataclass(slots=True)
class PublicarObraRequest:
    """Entrada del caso de uso PublicarObra."""

    obra_id: int
    propietario_id: int  # JWT del solicitante (debe ser el dueño)


@dataclass(slots=True)
class PublicarObraResponse:
    """Salida del caso de uso PublicarObra."""

    obra_id: int
    estado_visibilidad: str  # 'publicado'


class ObraNoPropiaError(PermissionError):
    """El usuario no es propietario de la obra — no puede publicar."""


class ObraNoEncontradaError(LookupError):
    """La obra no existe o el usuario no tiene acceso a ella."""


class PublicarObra:
    """Caso de uso: Publicar una obra (privado -> publicado)."""

    def __init__(self, obra_repo: ObraRepo, vector_repo: CorpusRepoVectorial) -> None:
        self._obra_repo = obra_repo
        self._vector_repo = vector_repo

    async def ejecutar(self, request: PublicarObraRequest) -> PublicarObraResponse:
        """Ejecuta la publicación.

        Raises:
            ObraNoPropiaError: si el adapter devuelve None (Regla 5
                aplicada: el caller no es propietario).
        """
        actualizada = await self._obra_repo.publicar(
            obra_id=request.obra_id,
            propietario_id=request.propietario_id,
        )
        if actualizada is None:
            # None puede ser: obra no existe OR el caller no es propietario.
            # ponytail: no diferenciamos para evitar information leak por
            # timing/oracle. El router mapea a 403 si ambos motivos, o
            # a 404 si quiere separar. Por defecto 403 (no autorizado).
            raise ObraNoPropiaError(
                f"Obra id={request.obra_id} no encontrada o el usuario "
                f"id={request.propietario_id} no es propietario."
            )

        await sincronizar_visibilidad_vectorial(
            self._vector_repo,
            actualizada.id,  # type: ignore[arg-type]
            actualizada.estado_visibilidad,
        )

        return PublicarObraResponse(
            obra_id=actualizada.id,  # type: ignore[arg-type]
            estado_visibilidad=actualizada.estado_visibilidad,
        )
