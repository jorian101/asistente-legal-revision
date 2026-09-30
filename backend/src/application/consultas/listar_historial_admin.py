"""Use case: ListarHistorialAdmin (solo admin).

Lista el historial RAG completo con filtros opcionales (usuario, expediente,
tipo de respuesta, rango de fechas y texto en la pregunta). No filtra por
propietario: es la vista de auditoria del administrador.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.consulta_historial_repo import ConsultaHistorialRepo


async def execute(
    repo: ConsultaHistorialRepo,
    *,
    usuario_id: int | None,
    expediente_id: int | None,
    tipo_respuesta: str | None,
    estado: str | None,
    fecha_desde: datetime | None,
    fecha_hasta: datetime | None,
    texto: str | None,
    pagina: int,
    por_pagina: int,
):
    """Lista el historial RAG completo con filtros (solo admin)."""
    return await repo.listar_admin(
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
