"""Helper de dominio: validación de `propietario_id`/`usuario_id` (Regla 5).

Sprint 4 — Regla 5 Trail of Bits: los adaptadores y use cases que leen o
modifican obras/obrados/chats privados/carpetas/documentos deben SIEMPRE
validar que el usuario ID sea un int > 0. No se confía en el input del
cliente (router) — el adapter lo vuelve a chequear.

El guard existe como primera línea de cada método de repo que opera por
propietario_id. Centralizarlo aquí evita 6+ copias idénticas (DRY) y
facilita el testeo del guard en aislamiento.
"""

from __future__ import annotations


def validar_propietario_id(propietario_id: int) -> None:
    """Valida que propietario_id sea int > 0 (Regla 5). Lanza ValueError si no.

    Rechaza:
        - bool (aunque isinstance(True, int) es True en Python, lo rechazamos
          porque True/False nunca son IDs válidos yRG5 no permite confianza
          en input del cliente).
        - int <= 0 (IDs auto-generados con IDENTITY empiezan en 1).
    """
    if (
        not isinstance(propietario_id, int)
        or isinstance(propietario_id, bool)
        or propietario_id <= 0
    ):
        raise ValueError("propietario_id es obligatorio y debe ser int > 0 (Regla 5).")


def validar_usuario_id(usuario_id: int) -> None:
    """Alias de validar_propietario_id para métodos que reciben `usuario_id`."""
    validar_propietario_id(usuario_id)
