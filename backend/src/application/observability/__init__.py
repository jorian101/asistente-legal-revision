"""Observabilidad del pipeline RAG (Sprint 7)."""

from src.application.observability.event_bus import (
    EventBus,
    InMemoryEventBus,
    get_event_bus,
)
from src.application.observability.pipeline_events import (
    EventoPipelineUnion,
    FaseCompletada,
    FaseIniciada,
    GeneracionCompletada,
    PipelineCompletado,
    PipelineError,
    fase_a_legible,
    resumen_legible_fase,
)

__all__ = [
    "EventBus",
    "InMemoryEventBus",
    "get_event_bus",
    "EventoPipelineUnion",
    "FaseCompletada",
    "FaseIniciada",
    "GeneracionCompletada",
    "PipelineCompletado",
    "PipelineError",
    "fase_a_legible",
    "resumen_legible_fase",
]
