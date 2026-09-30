"""Servicio: ConstructorMensajes — punto unico de armado de mensajes LLM (F2).

Convierte la plantilla resuelta (+ contexto del pipeline) en la estructura
{system, user} que cada adapter serializa segun su API. Muere el
_construir_prompt triplicado en cada adapter LLM.

Convencion de plantillas (opcional): si la plantilla contiene la linea
marcador `[SYSTEM]`, todo lo anterior es el mensaje de sistema y lo
posterior es el mensaje de usuario. Ninguna plantilla actual lo usa ->
backward compat (system=None).

Endpoint sin soporte de system (`soporta_system=false` en LLM_ENDPOINTS):
el system se pliega como prefijo del user en vez de descartarse.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.application.services.procesador_contexto import ProcesadorContexto
from src.domain.value_objects.contexto_expandido import ContextoExpandido

logger = logging.getLogger(__name__)

MARCA_SYSTEM = "[SYSTEM]"
SLOT_CONTEXTO = "{{contexto_expandido}}"

# ponytail: reserva fija para la salida dentro de la ventana. No cubre el peor
# caso a proposito: la salida mas larga medida (2.356 tokens) salio de un prompt
# truncado y puede crecer; si la salida la excede, Ollama hace context shift al
# FINAL de la generacion, que es menos grave que perder el contexto al inicio.
RESERVA_SALIDA = 2048

_ZWSP = "\u200b"
_LLAVE_DOBLE = re.compile(r"\{(?=\{)")


def neutralizar_tokens_plantilla(texto: str) -> str:
    """Rompe los tokens de protocolo del prompt en texto dinamico.

    Texto inyectado desde fuentes no confiables (memoria conversacional,
    consulta del usuario, contenido de documentos) no debe poder crear
    slots {{...}} vivos ni el marcador [SYSTEM]: se antepone un espacio
    de ancho cero al delimitador para que el texto se vea igual pero no
    sea interpretable como parte de la plantilla. Cubre corridas de
    llaves de cualquier longitud ({{{...}}} deja {{{...}}} sin slots
    vivos, no solo pares exactos).
    """
    texto = _LLAVE_DOBLE.sub("{" + _ZWSP, texto)
    return texto.replace(MARCA_SYSTEM, "[" + _ZWSP + "SYSTEM]")


@dataclass(frozen=True)
class MensajesLLM:
    """Estructura neutral de mensajes lista para serializar por provider."""

    system: str | None
    user: str


class ConstructorMensajes:
    """Arma {system, user} desde plantilla + ContextoExpandido."""

    def __init__(
        self,
        presupuesto_tokens: int = 4096,
        chars_por_token: float = 4.0,
        soporta_system: bool = True,
        ventana_tokens: int | None = None,
    ) -> None:
        self._presupuesto = presupuesto_tokens
        self._chars_por_token = chars_por_token
        self._soporta_system = soporta_system
        # Con ventana, el presupuesto del contexto se calcula por pedido contra
        # lo que deja libre la plantilla resuelta (A.1); sin ventana, fijo.
        self._ventana = ventana_tokens

    def construir(
        self,
        plantilla: str,
        contexto: ContextoExpandido,
        *,
        etiquetas_obra: Mapping[int, str] | None = None,
    ) -> MensajesLLM:
        """Resuelve slots y separa system/user.

        Args:
            plantilla: Plantilla ya resuelta por ResolvedorPlantilla
                (puede contener {{contexto_expandido}} y el marcador [SYSTEM]).
            contexto: Salida del pipeline RAG (Sprint 5).
            etiquetas_obra: Mapa obra_id -> etiqueta para ProcesadorContexto.

        Precondicion (contrato, revision PR #23): todo texto no confiable
        (memoria, consulta, contenido de documentos) debe pasar por
        neutralizar_tokens_plantilla() ANTES de armarse la plantilla. Un
        [SYSTEM] o {{slot}} crudo dentro de texto dinamico alteraria la
        separacion system/user o expandiria contexto duplicado (ver tests
        de contrato en test_constructor_mensajes.py).
        """
        system_crudo, plantilla_user = self._separar_system(plantilla)

        procesador = ProcesadorContexto(
            max_tokens=self._presupuesto_contexto(plantilla),
            chars_por_token=self._chars_por_token,
        )
        bloques = procesador.procesar(contexto, etiquetas_obra=etiquetas_obra)
        # [S#]: la regla de citado nombra los segmentos por número (verificable).
        contexto_str = "\n\n---\n\n".join(
            f"[S{i}] {b.renderizar()}" for i, b in enumerate(bloques, start=1)
        )
        user = plantilla_user.replace(SLOT_CONTEXTO, contexto_str)

        system = system_crudo.strip() if system_crudo is not None else None
        if system is not None and not self._soporta_system:
            user = f"{system}\n\n{user}"
            system = None
        self._avisar_si_excede(system, user)
        return MensajesLLM(system=system, user=user)

    def _tokens(self, texto: str) -> int:
        return int(len(texto) / self._chars_por_token)

    def _presupuesto_contexto(self, plantilla: str) -> int:
        """ventana − plantilla resuelta − reserva de salida, con el tope global."""
        if self._ventana is None:
            return self._presupuesto
        libre = self._ventana - self._tokens(plantilla.replace(SLOT_CONTEXTO, "")) - RESERVA_SALIDA
        return max(1, min(self._presupuesto, libre))

    def _avisar_si_excede(self, system: str | None, user: str) -> None:
        """Sin recorte de plantilla (decision del vocal): el desborde se avisa, no se oculta."""
        if self._ventana is None:
            return
        estimado = self._tokens((system or "") + user) + RESERVA_SALIDA
        if estimado > self._ventana:
            logger.warning(
                "Prompt excede la ventana del LLM: ~%d tokens (con %d de reserva de salida) "
                "sobre %d; el modelo truncara la entrada.",
                estimado,
                RESERVA_SALIDA,
                self._ventana,
            )

    @staticmethod
    def _separar_system(plantilla: str) -> tuple[str | None, str]:
        """Separa system/user sobre la PRIMERA marca [SYSTEM].

        Contrato: `plantilla` llega con el texto no confiable ya
        neutralizado; esta funcion no neutraliza nada por si misma.
        """
        if MARCA_SYSTEM not in plantilla:
            return None, plantilla
        antes, despues = plantilla.split(MARCA_SYSTEM, 1)
        return antes, despues.lstrip("\n")


__all__ = [
    "ConstructorMensajes",
    "MensajesLLM",
    "MARCA_SYSTEM",
    "SLOT_CONTEXTO",
    "neutralizar_tokens_plantilla",
]
