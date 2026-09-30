"""Use cases de auditoria (Trail of Bits R6).

registrar_auditoria: persiste una accion sensitiva (append-only).
listar_auditoria: consulta paginada para el panel admin.

Regla R6: acciones sensitivas (login, crear/eliminar entidades, publicar
borradores, indexar normas) DEBEN quedar trazadas con usuario y contexto.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.value_objects.registro_auditoria import RegistroAuditoria

if TYPE_CHECKING:
    from src.application.ports.audit_log_repo import AuditLogRepo

log = logging.getLogger(__name__)


async def registrar_auditoria(
    repo: AuditLogRepo,
    *,
    accion: str,
    usuario_id: int | None,
    entidad: str | None = None,
    entidad_id: int | None = None,
    detalle: dict | None = None,
) -> None:
    """Persiste un registro de auditoria (append-only).

    Ponytail: fire-and-forget seguro — nunca bloquea el flujo principal.
    Si el repo falla (DB caida), el error se propaga; los callers pueden
    envolver en try/except si la auditoria no debe derribar la accion.
    """
    await repo.registrar(
        RegistroAuditoria(
            accion=accion,
            usuario_id=usuario_id,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle,
        )
    )


async def registrar_auditoria_segura(repo: AuditLogRepo, **campos) -> None:
    """Como `registrar_auditoria`, pero un fallo de auditoria nunca derriba la accion.

    La accion ya se hizo: si el repo falla (BD caida) solo se registra en el log,
    en vez de esconderlo con un `except: pass`. `campos` son los de registrar_auditoria.
    """
    try:
        await registrar_auditoria(repo, **campos)
    except Exception:  # noqa: BLE001 — best-effort, pero con rastro
        log.warning("No se pudo registrar la auditoria (%s)", campos.get("accion"), exc_info=True)


async def listar_auditoria(
    repo: AuditLogRepo,
    accion: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RegistroAuditoria]:
    """Lista registros de auditoria (mas recientes primero)."""
    return await repo.listar(accion=accion, limit=limit, offset=offset)
