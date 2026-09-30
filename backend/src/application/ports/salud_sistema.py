"""Port: SaludSistemaRepo — verificación de infraestructura (HU-22).

Permite al use case ObtenerMetricasSalud consultar el estado de los
componentes de infraestructura del pipeline RAG sin conocer detalles
de PostgreSQL ni Qdrant.

Los checks deben ser no-throw: ante caída devuelven ok=False, nunca
excepción (la salud reporta la caída, no la sufre).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SaludInfraestructura:
    """Estado de los componentes de infraestructura.

    Atributos:
        postgres_ok: True si PostgreSQL responde a SELECT 1.
        qdrant_ok: True si Qdrant responde y la colección corpus_juridico
            es accesible.
        qdrant_puntos: Cantidad de puntos en la colección. 0 si no se
            pudo consultar.
    """

    postgres_ok: bool
    qdrant_ok: bool
    qdrant_puntos: int


class SaludSistemaRepo(Protocol):
    """Verificación de salud de PostgreSQL + Qdrant."""

    async def verificar(self) -> SaludInfraestructura:
        """Ejecuta los pings y retorna el estado agregado.

        Nunca lanza: cada componente caído se reporta con ok=False.
        """
        ...
