"""Repositorio PostgreSQL: AuditLogRepo.

Implementa el puerto application.ports.AuditLogRepo (Trail of Bits R6).
Tabla append-only: registrar() inserta, listar() lee. Nunca UPDATE/DELETE.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.audit_log import AuditLogModel
from src.application.ports.audit_log_repo import AuditLogRepo
from src.domain.value_objects.registro_auditoria import RegistroAuditoria


class AuditLogRepoImpl(AuditLogRepo):
    """Implementacion PostgreSQL de la auditoria."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def registrar(self, registro: RegistroAuditoria) -> None:
        """Inserta un registro de auditoria (append-only)."""
        model = AuditLogModel(
            accion=registro.accion,
            entidad=registro.entidad,
            entidad_id=registro.entidad_id,
            usuario_id=registro.usuario_id,
            detalle=registro.detalle,
        )
        self._session.add(model)
        await self._session.flush()
        # Commit explicito: AsyncSession no autocommitea (mismo patron que
        # consulta_historial_repo — ver test_explicit_commit).
        await self._session.commit()

    async def listar(
        self,
        accion: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RegistroAuditoria]:
        """Lista registros mas recientes primero, filtrable por accion."""
        stmt = select(AuditLogModel)
        if accion is not None:
            stmt = stmt.where(AuditLogModel.accion == accion)
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()

        return [
            RegistroAuditoria(
                accion=m.accion,
                usuario_id=m.usuario_id,
                entidad=m.entidad,
                entidad_id=m.entidad_id,
                detalle=m.detalle,
                created_at=m.created_at,
            )
            for m in rows
        ]


def get_audit_log_repo(session: AsyncSession) -> AuditLogRepoImpl:
    """Factory del AuditLogRepoImpl."""
    return AuditLogRepoImpl(session)
