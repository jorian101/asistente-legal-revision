"""Sincroniza la visibilidad de una obra hacia Qdrant (F-12).

PostgreSQL es la fuente de verdad del `estado_visibilidad`; el filtro de
privacidad de Qdrant (Regla 4) lee el payload `visibilidad` de los puntos, que
solo se fija al indexar. Cada cambio de visibilidad debe reflejarse aca.
"""

from __future__ import annotations

import logging

from src.application.ports.corpus_vectorial import CorpusRepoVectorial

log = logging.getLogger(__name__)


async def sincronizar_visibilidad_vectorial(
    vector_repo: CorpusRepoVectorial, obra_id: int, visibilidad: str
) -> None:
    """Best-effort: PG ya cambio; si Qdrant falla se registra y no se revierte."""
    try:
        await vector_repo.actualizar_visibilidad_obra(obra_id, visibilidad)
    except Exception:  # noqa: BLE001 — no deshacer el cambio ya commiteado en PG
        log.exception(
            "No se pudo sincronizar la visibilidad en Qdrant (obra_id=%s, visibilidad=%s)",
            obra_id,
            visibilidad,
        )
