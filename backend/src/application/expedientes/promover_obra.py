"""Use case: PromoverObra — un obrado publicado pasa a ser jurisprudencia.

Los obrados de casos (sentencias, autos, dictámenes) pueden volverse
jurisprudencia: el operador propone y el supervisor aprueba (o promueve
directamente). Al aprobar, la obra queda `tipo_documento='jurisprudencia'` y
`estado_visibilidad='global'`: cualquier usuario la recupera como jurisprudencia.

La propuesta se marca en `obra.estado_validacion` (sin tabla nueva):
`promocion_pendiente` -> `promovida` | `promocion_rechazada`.

Los autos de vista oficializados no pasan por aquí: `aprobar_oficial` ya crea su
ejemplo global (N4), que la categoría de fuente trata como jurisprudencia.
"""

from __future__ import annotations

import logging

from src.application.expedientes.eliminar_obra import ObraNoEncontradaError
from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.obra_repo import ObraRepo
from src.domain.services.categoria_fuente import categoria_de_obra

log = logging.getLogger(__name__)

PENDIENTE = "promocion_pendiente"
RECHAZADA = "promocion_rechazada"
PROMOVIDA = "promovida"


class ObraNoPromovibleError(ValueError):
    """La obra no cumple los requisitos para promoverse."""


class PromoverObra:
    """Operador propone, supervisor resuelve (aprueba o rechaza)."""

    def __init__(self, obra_repo: ObraRepo, vector_repo: CorpusRepoVectorial) -> None:
        self._obra_repo = obra_repo
        self._vector_repo = vector_repo

    async def _obra_promovible(self, obra_id: int, usuario_id: int):
        obra = await self._obra_repo.obtener(obra_id, usuario_id)
        if obra is None:
            raise ObraNoEncontradaError(f"Obra id={obra_id} no encontrada.")
        if categoria_de_obra(obra.tipo_documento) != "obrado":
            raise ObraNoPromovibleError("Solo un obrado del expediente puede promoverse.")
        if obra.estado_visibilidad != "publicado":
            raise ObraNoPromovibleError("El obrado debe estar publicado antes de promoverse.")
        if obra.estado_validacion in (PROMOVIDA,):
            raise ObraNoPromovibleError("El obrado ya fue promovido.")
        return obra

    async def proponer(self, *, obra_id: int, usuario_id: int):
        """El propietario propone promover su obrado; queda pendiente."""
        obra = await self._obra_promovible(obra_id, usuario_id)
        if obra.propietario_id != usuario_id:
            raise PermissionError("Solo el propietario propone la promoción de su obrado.")
        if obra.estado_validacion == PENDIENTE:
            raise ObraNoPromovibleError("La promoción ya está pendiente de aprobación.")
        return await self._obra_repo.marcar_promocion(obra_id, PENDIENTE)

    async def resolver(
        self,
        *,
        obra_id: int,
        aprobar: bool,
        actor_id: int,
        motivo: str | None = None,
    ):
        """El supervisor aprueba (o promueve directamente) o rechaza con motivo."""
        if not aprobar and not motivo:
            raise ValueError("motivo es obligatorio para rechazar.")
        await self._obra_promovible(obra_id, actor_id)
        if not aprobar:
            return await self._obra_repo.marcar_promocion(obra_id, RECHAZADA, motivo)

        promovida = await self._obra_repo.promover_a_jurisprudencia(obra_id)
        try:
            await self._vector_repo.actualizar_payload_obra(
                obra_id,
                {
                    "tipo_documento": "jurisprudencia",
                    "tipo_fuente": "jurisprudencia",
                    "visibilidad": "global",
                },
            )
        except Exception:  # noqa: BLE001 — PG ya cambio; no se revierte
            log.exception("No se pudo sincronizar la promoción en Qdrant (obra_id=%s)", obra_id)
        return promovida
