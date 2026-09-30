"""Subscriber de consola para traza visual del pipeline RAG (solo dev).

Escucha eventos del EventBus e imprime barras de progreso Unicode por fase.
Solo se inicia si LOG_LEVEL=DEBUG o ENV=dev/development.
"""

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.observability.event_bus import EventBus

# Pesos porcentuales de inicio de cada fase (para barra progresiva)
_PESOS_INICIO: dict[str, int] = {
    "entendiendo": 40,
    "buscando": 50,
    "reordenando": 50,
    "expandiendo": 50,
    "generando": 50,
}


def _barra(pct: int, ancho: int = 20) -> str:
    """Genera barra Unicode de ancho fijo."""
    llenos = int((pct / 100) * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


async def iniciar_console_subscriber(bus: "EventBus") -> None:
    """Escucha eventos del EventBus e imprime barras de progreso Unicode."""
    # Import lazy para evitar ciclos
    from src.application.observability.pipeline_events import (
        FaseCompletada,
        FaseIniciada,
        PipelineCompletado,
        PipelineError,
        fase_a_legible,
    )

    consultas_vistas: set[int] = set()

    async for evento in bus.subscribe():
        if isinstance(evento, FaseIniciada):
            if evento.consulta_id not in consultas_vistas:
                consultas_vistas.add(evento.consulta_id)
                sys.stdout.write(f"\nCONSULTA #{evento.consulta_id}\n")
            pct = _PESOS_INICIO.get(evento.fase, 40)
            sys.stdout.write(f"\r{_barra(pct)} {pct:3d}% {fase_a_legible(evento.fase)}")
            sys.stdout.flush()

        elif isinstance(evento, FaseCompletada):
            sys.stdout.write(f"\r{_barra(100)} 100% {fase_a_legible(evento.fase)}\n")
            sys.stdout.flush()

        elif isinstance(evento, PipelineCompletado):
            tipo = evento.tipo_respuesta or "general"
            sys.stdout.write(
                f"Completado en {evento.latencia_total_ms:,}ms · "
                f"{evento.fragmentos_count} fragmentos · {tipo}\n\n"
            )
            sys.stdout.flush()

        elif isinstance(evento, PipelineError):
            sys.stdout.write(f"\r[ERROR] {evento.fase_fallida}: {evento.mensaje_error}\n\n")
            sys.stdout.flush()
