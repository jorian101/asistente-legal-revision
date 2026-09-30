"""Use case: ObtenerMetricasSalud — HU-22 salud de infraestructura.

Completa el gap de ObtenerMetricasRendimiento: estado de PostgreSQL,
Qdrant (con conteo de puntos del corpus) y sesiones activas (suscriptores
SSE de la Sala de Control). Complementa /admin/metricas/contexto
(expansión) y /admin/dashboard/resumen (uso).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.observability.event_bus import InMemoryEventBus
from src.application.ports.salud_sistema import SaludSistemaRepo


@dataclass(frozen=True, slots=True)
class MetricasSalud:
    """Salud agregada del sistema.

    Atributos:
        postgres_ok: PostgreSQL responde.
        qdrant_ok: Qdrant responde con la colección corpus_juridico accesible.
        qdrant_puntos: Puntos indexados en corpus_juridico (0 si caído).
        sesiones_activas: Suscriptores SSE vivos del bus de eventos.
    """

    postgres_ok: bool
    qdrant_ok: bool
    qdrant_puntos: int
    sesiones_activas: int


async def ejecutar(
    salud_repo: SaludSistemaRepo,
    bus: InMemoryEventBus,
) -> MetricasSalud:
    """Consulta el estado de infraestructura y el bus de eventos.

    Args:
        salud_repo: Port de verificación PG/Qdrant (adapter SaludSistemaImpl).
        bus: Bus in-memory de eventos del pipeline (singleton app).

    Returns:
        MetricasSalud con el estado de cada componente.
    """
    infra = await salud_repo.verificar()
    return MetricasSalud(
        postgres_ok=infra.postgres_ok,
        qdrant_ok=infra.qdrant_ok,
        qdrant_puntos=infra.qdrant_puntos,
        sesiones_activas=bus.cantidad_suscriptores(),
    )
