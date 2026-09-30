"""Servicio: ConstructorMemoriaConversacional — memoria del chat activo (F3).

Fuente de verdad: MensajeChat del chat (chat_privado), NO consulta_historial
(log inmutable de auditoria). Implementa "Gestion del contexto" de la
taxonomia de ingenieria de contexto: memoria multi-interaccion sin saturar
la ventana.

Estrategia v1 (ponytail): ventana deslizante VERBATIM de los turnos mas
recientes dentro de un presupuesto de caracteres. Nunca parafrasea
(anti telephone-game). El resumen anclado incremental con LLM se agrega
AQUI cuando el uso real muestre chats que exceden la ventana:
# ponytail: ventana verbatim; resumen ancado con LLM si chats reales > presupuesto

Borradores: si la consulta menciona "borrador", se inyecta el contenido
ACTUAL del borrador ligado al chat (borrador_repo.obtener_por_chat) — nunca
el texto congelado de un turno anterior, porque el borrador puede haber sido
editado o publicado (anti stale-memory poisoning).

Regla 4/5: todo filtro lleva usuario_id; el repo es la frontera.
"""

from __future__ import annotations

import re

from src.application.ports.borrador_repo import BorradorRepo
from src.application.ports.mensaje_chat_repo import MensajeChatRepo

_MAX_MENSAJE_CHARS = 800
_MAX_BORRADOR_CHARS = 1500

_FIN_ORACION = re.compile(r"[.!?…]\s+|\n{2,}")


def truncar_por_oracion(texto: str, limite: int) -> str:
    """Trunca al limite cortando en frontera de oracion, no a mitad de frase.

    Un corte ciego a mitad de oracion envenena la memoria (el LLM lee texto
    roto como si fuera real). Si no hay frontera dentro del limite, corta
    duro y marca con "…" para que el corte sea visible.
    """
    if len(texto) <= limite:
        return texto
    ventana = texto[:limite]
    cortes = list(_FIN_ORACION.finditer(ventana))
    if cortes:
        return ventana[: cortes[-1].end()].rstrip()
    return ventana.rstrip() + "…"


class ConstructorMemoriaConversacional:
    """Arma el bloque {{historial_conversacion}} desde MensajeChat."""

    def __init__(
        self,
        mensaje_repo: MensajeChatRepo,
        borrador_repo: BorradorRepo | None = None,
        max_chars: int = 6000,
    ) -> None:
        self._mensajes = mensaje_repo
        self._borradores = borrador_repo
        self._max_chars = max_chars

    async def construir(self, chat_id: int, usuario_id: int, consulta_actual: str) -> str:
        """Devuelve la memoria del chat lista para inyectar. "" si no hay nada.

        Args:
            chat_id: Chat activo.
            usuario_id: Propietario (Regla 4/5 — filtra el repo).
            consulta_actual: Consulta del turno actual (detecta mencion de borrador).
        """
        items, _total = await self._mensajes.listar_por_chat(
            chat_id, usuario_id, pagina=1, por_pagina=500
        )

        lineas_nuevas: list[str] = []
        usados = 0
        for mensaje in reversed(items):  # del mas reciente al mas viejo
            rol = "Usuario" if mensaje.tipo == "user" else "Asistente"
            texto = truncar_por_oracion(mensaje.contenido, _MAX_MENSAJE_CHARS)
            linea = f"{rol}: {texto}"
            costo = len(linea) + 1
            if lineas_nuevas and usados + costo > self._max_chars:
                break
            lineas_nuevas.append(linea)
            usados += costo

        partes = list(reversed(lineas_nuevas))  # orden cronologico

        if self._borradores is not None and "borrador" in consulta_actual.lower():
            borrador = await self._borradores.obtener_por_chat(chat_id, usuario_id)
            if borrador is not None:
                contenido = truncar_por_oracion(borrador.contenido or "", _MAX_BORRADOR_CHARS)
                partes.append(f"[BORRADOR ACTUAL DE ESTE CHAT]\n{contenido}")

        return "\n\n".join(partes)


__all__ = ["ConstructorMemoriaConversacional"]
