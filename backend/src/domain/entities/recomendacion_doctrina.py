"""Entidad de dominio: RecomendacionDoctrina.

Recomendación de una doctrina global a un expediente específico. El supervisor
auto-aprueba su recomendación; el operador propone y el supervisor aprueba.

Estados:
- 'recomendada': aprobada (visible en la sección "Recomendadas para este
  expediente" del chat).
- 'pendiente': propuesta por un operador, esperando aprobación del supervisor.
- 'rechazada': rechazada por el supervisor (con motivo).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EstadoRecomendacion = Literal["recomendada", "pendiente", "rechazada"]


@dataclass(slots=True)
class RecomendacionDoctrina:
    id: int | None
    obra_global_id: int | None
    expediente_id: int
    recomendado_por: int
    estado: EstadoRecomendacion
    aprobado_por: int | None = None
    motivo_rechazo: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Recomendación por corpus N2/N3 (norma global, sin obra): exactamente
    # uno de (obra_global_id | corpus+corpus_ref) va no-nulo.
    corpus: str | None = None
    corpus_ref: str | None = None
