"""Port: AuditLogRepo — persistencia de auditoria (Trail of Bits R6).

El use case RegistroAuditoria depende de este Protocol (dependency
inversion: la interfaz vive en application, la impl en adapters).
"""

from __future__ import annotations

from typing import Protocol

from src.domain.value_objects.registro_auditoria import RegistroAuditoria


class AuditLogRepo(Protocol):
    """Repo de la tabla audit_log (append-only)."""

    async def registrar(self, registro: RegistroAuditoria) -> None:
        """Persiste un registro de auditoria. No devuelve id (append-only)."""
        ...

    async def listar(
        self,
        accion: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RegistroAuditoria]:
        """Lista registros (mas recientes primero), filtrable por accion."""
        ...
