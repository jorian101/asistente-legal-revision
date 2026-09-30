"""Use cases de consultas (Sprint 3 — Motor de Recuperacion RAG)."""

from src.application.consultas.clasificar_tipo_respuesta import (
    clasificar_tipo_respuesta,
)
from src.application.consultas.recuperar_contexto import (
    ConsultaRequest,
    ResultadoConsulta,
    ejecutar,
)

__all__ = [
    "ConsultaRequest",
    "ResultadoConsulta",
    "clasificar_tipo_respuesta",
    "ejecutar",
]
