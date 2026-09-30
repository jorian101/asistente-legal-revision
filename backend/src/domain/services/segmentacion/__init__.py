"""Dominio: Servicios de segmentacion de normas juridicas.

Este paquete contiene la estrategia de segmentacion por corpus (Strategy Pattern):
- base.py: Clase abstracta SegmentadorNorma + Value Objects
- registro.py: Registry para resolver segmentador por abreviatura
- cppm.py, cpm.py, cpe.py, lojm.py, lofa.py, ley1970.py: Implementaciones concretas
- scp.py, cidh.py: Jurisprudencia vinculante (hecho/derecho/fallo)
"""

from __future__ import annotations

import src.domain.services.segmentacion.cidh  # noqa: F401, E402

# Auto-registro de segmentadores concretos (efecto lateral al importar)
import src.domain.services.segmentacion.cpe  # noqa: F401, E402
import src.domain.services.segmentacion.cpm  # noqa: F401, E402
import src.domain.services.segmentacion.cppm  # noqa: F401, E402
import src.domain.services.segmentacion.doctrina  # noqa: F401, E402
import src.domain.services.segmentacion.generico  # noqa: F401, E402
import src.domain.services.segmentacion.ley1970  # noqa: F401, E402
import src.domain.services.segmentacion.lofa  # noqa: F401, E402
import src.domain.services.segmentacion.lojm  # noqa: F401, E402
import src.domain.services.segmentacion.scp  # noqa: F401, E402
from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

__all__ = [
    "FragmentoProducible",
    "ArbolJerarquico",
    "NodoJerarquico",
    "SegmentadorNorma",
    "SegmentadorRegistry",
]
