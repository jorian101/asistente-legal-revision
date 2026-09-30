"""Router admin: auditoria del historial de consultas RAG (Task 8b).

Endpoints (solo admin):
- GET    /admin/consultas/historial       — listado con filtros + paginacion
- DELETE /admin/consultas/historial/{id}  — soft delete de cualquier entrada

CRUD deliberadamente sin create/update: es un log de auditoria inmutable
(las entradas las genera el pipeline RAG).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    ConsultaHistorialRepoDep,
    require_permiso,
)
from src.application.admin.audit import registrar_auditoria_segura
from src.application.consultas.eliminar_historial_admin import (
    execute as eliminar_historial_admin,
)
from src.application.consultas.listar_historial_admin import (
    execute as listar_historial_admin,
)
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/admin/consultas", tags=["admin", "consultas"])


class HistorialAdminItemDTO(BaseModel):
    id: int
    expediente_id: int | None
    usuario_id: int
    usuario_carnet: str
    usuario_nombre: str
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    latencia_ms: int | None
    modelo_llm: str | None
    created_at: str | None


class PaginaHistorialAdminDTO(BaseModel):
    items: list[HistorialAdminItemDTO]
    total: int
    pagina: int
    por_pagina: int


@router.get("/historial", response_model=PaginaHistorialAdminDTO)
async def get_historial_admin(
    _: Annotated[Usuario, Depends(require_permiso("consultas_rag", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    usuario_id: int | None = Query(None),
    expediente_id: int | None = Query(None),
    tipo_respuesta: str | None = Query(None),
    estado: str | None = Query(None),
    fecha_desde: Annotated[datetime | None, Query()] = None,
    fecha_hasta: Annotated[datetime | None, Query()] = None,
    texto: str | None = Query(None),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=100),
) -> PaginaHistorialAdminDTO:
    """Lista el historial RAG completo con filtros (solo admin)."""
    items, total = await listar_historial_admin(
        historial_repo,
        usuario_id=usuario_id,
        expediente_id=expediente_id,
        tipo_respuesta=tipo_respuesta,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        texto=texto,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return PaginaHistorialAdminDTO(
        items=[
            HistorialAdminItemDTO(
                id=i.id,
                expediente_id=i.expediente_id,
                usuario_id=i.usuario_id,
                usuario_carnet=i.usuario_carnet,
                usuario_nombre=i.usuario_nombre,
                pregunta=i.pregunta,
                respuesta=i.respuesta,
                tipo_respuesta=i.tipo_respuesta,
                latencia_ms=i.latencia_ms,
                modelo_llm=i.modelo_llm,
                created_at=i.created_at.isoformat() if i.created_at else None,
            )
            for i in items
        ],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.delete(
    "/historial/{historial_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar entrada del historial (soft delete, solo admin)",
)
async def delete_historial_admin(
    historial_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("consultas_rag", "eliminar"))],
    historial_repo: ConsultaHistorialRepoDep,
    audit_repo: AuditLogRepoDep,
) -> None:
    """Soft delete de una entrada del historial (sin chequeo de propietario)."""
    eliminado = await eliminar_historial_admin(
        historial_repo,
        historial_id=historial_id,
    )
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada de historial no encontrada.",
        )
    await registrar_auditoria_segura(
        audit_repo,
        accion="eliminar_consulta_admin",
        usuario_id=current_user.id,
        entidad="consulta_historial",
        entidad_id=historial_id,
    )
