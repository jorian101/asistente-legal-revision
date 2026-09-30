"""Trabajos de indexado: consultar estado y cancelar.

Un indexado tarda minutos, asi que el endpoint que lo lanza responde 202 con el
id del trabajo y el cliente consulta aca. Solo quien lanzo el trabajo (o un
administrador) puede cancelarlo; para el resto el trabajo no existe.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.adapters.http.dependencies import get_current_user
from src.application.services.trabajos_indexado import (
    CancelacionNoPermitidaError,
    JobInexistenteError,
    JobYaTerminadoError,
    estado_publico,
    registro,
)
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/jobs", tags=["jobs"])


class TrabajoEncoladoResp(BaseModel):
    """Indexado encolado: el cliente sigue el estado en /jobs/{job_id}."""

    job_id: str
    estado: str


def _no_encontrado() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo no encontrado.")


def _es_admin(usuario: Usuario) -> bool:
    return usuario.rol == "administrador"


@router.get("/{job_id}", response_model=dict, summary="Estado de un trabajo de indexado")
async def get_job(
    job_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> dict:
    job = registro.obtener(job_id)
    # 404 y no 403: no revelamos que existe un trabajo de otro usuario.
    if job is None or (job.usuario_id != current_user.id and not _es_admin(current_user)):
        raise _no_encontrado()
    return estado_publico(job)


@router.post("/{job_id}/cancel", response_model=dict, summary="Cancelar un trabajo de indexado")
async def post_cancel(
    job_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> dict:
    try:
        job = registro.cancelar(
            job_id, usuario_id=current_user.id, es_admin=_es_admin(current_user)
        )
    except JobInexistenteError as exc:
        raise _no_encontrado() from exc
    except CancelacionNoPermitidaError as exc:
        # Mismo 404 que el GET: para el resto, el trabajo no existe.
        raise _no_encontrado() from exc
    except JobYaTerminadoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return estado_publico(job)
