"""Tests del adapter PostgreSQL ConsultaHistorialRepoImpl.

Patrón tests/borradores/test_borrador_repo.py: MagicMock session + compile
del statement capturado (el SQL que el repo envía a la BD es el contrato).
Focus: los desgloses de resumen_dashboard (por_estado/por_tipo/por_modelo/
por_usuario/consultas_por_dia) DEBEN filtrar activo = true igual que el
total_consultas; sin el filtro cuentan consultas soft-deleted y las sumas
superan el headline del dashboard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.adapters.postgres.repos.consulta_historial_repo import (
    ConsultaHistorialRepoImpl,
)


def _session_capturando_stmts(total: int) -> tuple[MagicMock, list]:
    """Session mockeada que registra cada stmt ejecutado por resumen_dashboard.

    La 1ra query (count del total) responde scalar() = total; los agregados
    posteriores responden filas vacías.
    """
    stmts: list = []

    def _execute(stmt):
        stmts.append(stmt)
        result = MagicMock()
        result.scalar.return_value = total
        result.all.return_value = []
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    return session, stmts


async def test_resumen_dashboard_agregados_filtran_activo():
    session, stmts = _session_capturando_stmts(total=3)
    repo = ConsultaHistorialRepoImpl(session)

    resumen = await repo.resumen_dashboard()

    # 1 count del total + 5 agregados (estados/tipos/modelos/usuarios/dias).
    assert len(stmts) == 6
    for stmt in stmts[1:]:
        sql = str(stmt.compile())
        assert "activo" in sql, f"agregado sin filtro soft-delete activo: {sql}"
    assert resumen.total_consultas == 3
