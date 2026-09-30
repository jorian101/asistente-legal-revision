"""Interactor: PublicarBorrador — Caso de uso publicar borrador.

Sprint 6 Fase 1.1. Cambia estado 'borrador' -> 'publicado'.

Regla 7 Trail of Bits (BLOQUEANTE): el filtro de propietario vive en el
ADAPTER (BorradorRepo.actualizar_estado valida propietario_id). Este use
case solo pasa `usuario_id` (JWT). Si el caller no es propietario, el
adapter devuelve None y este use case levanta BorradorNoPropioError
(403 en router).

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados.

Test BLOQUEANTE: tests/borradores/test_publicar_borrador.py
- test_borrador_publicado_por_otro_usuario_falla (Regla 7)
- test_borrador_publicado_por_propietario_ok
- test_publicar_borrador_ya_publicado_idempotente
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.borrador_repo import BorradorRepo
from src.domain.exceptions import BorradorNoPropioError, BorradorVacioError


@dataclass(slots=True)
class PublicarBorradorRequest:
    """Entrada del caso de uso PublicarBorrador."""

    borrador_id: int
    propietario_id: int  # JWT del solicitante (debe ser el dueño)


@dataclass(slots=True)
class PublicarBorradorResponse:
    """Salida del caso de uso PublicarBorrador."""

    borrador_id: int
    estado: str  # 'publicado'


class PublicarBorrador:
    """Caso de uso: Publicar un borrador (borrador -> publicado)."""

    def __init__(self, borrador_repo: BorradorRepo) -> None:
        self._borrador_repo = borrador_repo

    async def ejecutar(self, request: PublicarBorradorRequest) -> PublicarBorradorResponse:
        """Ejecuta la publicacion.

        Raises:
            BorradorNoPropioError: si el adapter devuelve None (Regla 7
                aplicada: el caller no es propietario o el borrador no
                existe). Mismo mensaje para ambos casos — evitar info leak.
            BorradorVacioError: si el borrador existe y es del caller pero
                su contenido esta vacio (no se genero/transmitio). Previene
                publicar borrador vacio/incompleto (incluido tras cancelar
                el stream LLM).
        """
        # FIX R2 (no-mistakes codex round 3): validar contenido NO vacio
        # antes de cambiar estado. El borrador se persiste con contenido=""
        # antes del stream; sin esto el propietario puede publicar vacio.
        existente = await self._borrador_repo.obtener_por_id(request.borrador_id)
        if existente is None or existente.propietario_id != request.propietario_id:
            # ponytail: mismo mensaje para ambos casos — evitar oracle.
            raise BorradorNoPropioError(
                f"Borrador id={request.borrador_id} no encontrado o el "
                f"usuario id={request.propietario_id} no es propietario."
            )
        if not existente.contenido or not existente.contenido.strip():
            raise BorradorVacioError(
                f"Borrador id={request.borrador_id} no tiene contenido "
                f"generado. Genere el borrador completo antes de publicar."
            )

        actualizado = await self._borrador_repo.actualizar_estado(
            borrador_id=request.borrador_id,
            estado="publicado",
            propietario_id=request.propietario_id,
        )
        if actualizado is None:
            # None: borrador no existe OR caller no es propietario.
            # ponytail: mismo mensaje para ambos (evitar oracle de timing).
            raise BorradorNoPropioError(
                f"Borrador id={request.borrador_id} no encontrado o el "
                f"usuario id={request.propietario_id} no es propietario."
            )

        return PublicarBorradorResponse(
            borrador_id=actualizado.id,  # type: ignore[arg-type]
            estado=actualizado.estado,
        )
