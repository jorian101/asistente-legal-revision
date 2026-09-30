"""Use case: EliminarObra (CRUD-1).

Valida propiedad (Regla 5: solo dueño o admin), elimina físicamente la obra de PostgreSQL,
y limpia vectores en Qdrant + fragmentos en DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.corpus_vectorial import VectorRepo
    from src.application.ports.fragmento_repo import FragmentoRepo
    from src.application.ports.obra_repo import ObraRepo


class ObraNoEncontradaError(Exception):
    """La obra no existe o no pertenece al expediente."""


class ObraNoPropiaError(Exception):
    """El usuario no es propietario de la obra y no es admin."""


async def eliminar_obra(
    obra_repo: ObraRepo,
    fragmento_repo: FragmentoRepo,
    vector_repo: VectorRepo,
    *,
    expediente_id: int,
    obra_id: int,
    solicitante_id: int,
    es_admin: bool = False,
) -> bool:
    """Elimina una obra. Valida propietario y limpia fragmentos y vectores."""
    # Obtenemos la obra pasando solicitante_id (o 0 si es admin para omitir filtro de visibilidad)
    obra = await obra_repo.obtener(
        obra_id, usuario_id=solicitante_id if not es_admin else solicitante_id
    )
    if obra is None and es_admin:
        # Re-intentar obtener por ids batch sin Regla 5 si es admin
        obras_dict = await obra_repo.obtener_por_ids([obra_id], usuario_id=solicitante_id)
        obra = obras_dict.get(obra_id)

    if obra is None or obra.expediente_id != expediente_id:
        raise ObraNoEncontradaError(
            f"Obra id={obra_id} no encontrada en expediente id={expediente_id}."
        )

    if not es_admin and obra.propietario_id != solicitante_id:
        raise ObraNoPropiaError(
            f"Usuario id={solicitante_id} no es propietario de la obra id={obra_id}."
        )

    # 1. Borrar vectores Qdrant + fragmentos DB (mismo patrón que indexar_obra.py)
    await vector_repo.delete_by_obra(obra_id)
    await fragmento_repo.delete_by_obra(obra_id)

    # 2. Borrar de ObraRepo
    eliminado = await obra_repo.eliminar(obra_id)
    return eliminado
