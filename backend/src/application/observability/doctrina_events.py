"""Eventos de dominio de doctrina (Plan A).

Eventos inmutables que viajan por el EventBus (in-memory) para que el panel
del supervisor vea en vivo las propuestas/aprobaciones de doctrina sin
refrescar. Reutiliza el mismo bus de observabilidad (Sprint 7).

No se persisten: solo entrega en vivo a subscriptores SSE conectados.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DoctrinaPropuesta:
    """Un operador propuso una doctrina ('publicado' — pendiente de aceptación)."""

    obra_id: int
    usuario_id: int
    usuario_nombre: str
    nombre_archivo: str
    expediente_id: int | None
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class DoctrinaAprobada:
    """El supervisor aprobó una doctrina ('publicado' -> 'global')."""

    obra_id: int
    usuario_id: int
    usuario_nombre: str
    nombre_archivo: str
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class DoctrinaRechazada:
    """El supervisor rechazó una doctrina ('publicado' -> 'rechazado')."""

    obra_id: int
    usuario_id: int
    usuario_nombre: str
    nombre_archivo: str
    motivo: str
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class DoctrinaGlobalCargada:
    """El supervisor cargó una doctrina global directa (auto-aprobación)."""

    obra_id: int
    usuario_id: int
    usuario_nombre: str
    nombre_archivo: str
    timestamp_ms: int
