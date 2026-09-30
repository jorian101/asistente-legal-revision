"""Domain service: ExtraerAgravios — extracción de agravios del recurso (P5).

Pure domain logic: detecta los agravios planteados por el recurrente en los
fragmentos del contexto (autos de vista de apelación incidental/restringida).

Los autos reales del TSJM estructuran los agravios con el patron:

    **AGRAVIO 1:** <texto del agravio>
    **AGRAVIO 2:** <texto> ...
    ...
    **AGRAVIO 9:** <texto>

(ver `sources/casos-tsjm/casos/exp-3145-3172-apelacion-incidental/
documentos/auto_de_vista_04_2026.md` — caso Salinas, 9 agravios).

Sin I/O, sin DI, testable puro. El extractor recorre el texto concatenado
de los fragmentos del contexto y devuelve los agravios numerados que
encuentre (hasta 20, defensivo contra documentos mal formados).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patron: "AGRAVIO N:" (acepta ** negritas, numeros 1-2 digitos, opcional punto).
_PATRON_AGRAVIO = re.compile(
    r"\*\*?\s*AGRAVIO\s+(\d{1,2})\s*:\s*\*\*?\s*(.+?)(?=\s*\*\*?\s*AGRAVIO\s+\d{1,2}\s*:|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_MAX_AGRAVIOS = 20


@dataclass(frozen=True, slots=True)
class AgravioProcesal:
    """Un agravio del recurrente extraído del contexto.

    Atributos:
        numero: Número del agravio (1-based).
        texto: Texto del agravio (recortado a ~300 chars).
        fragmento_id: ID del fragmento origen (trazabilidad). None si no aplica.
    """

    numero: int
    texto: str
    fragmento_id: int | None = None


def extraer_agravios(fragmentos: list) -> list[AgravioProcesal]:
    """Extrae agravios del recurrente desde una lista de fragmentos.

    Args:
        fragmentos: Lista de objetos con `.texto` (y opcional `.id`).
            Se concatenan los textos y se buscan patrones "AGRAVIO N:".

    Returns:
        Lista de AgravioProcesal ordenada por número. Vacía si no se
        detecta ningún agravio.
    """
    if not fragmentos:
        return []

    texto_completo = "\n".join(f.texto for f in fragmentos if getattr(f, "texto", None))
    if not texto_completo.strip():
        return []

    agravios: list[AgravioProcesal] = []
    for match in _PATRON_AGRAVIO.finditer(texto_completo):
        numero = int(match.group(1))
        if numero > _MAX_AGRAVIOS:
            continue
        texto = " ".join(match.group(2).split())
        agravios.append(
            AgravioProcesal(
                numero=numero,
                texto=texto[:300],
                fragmento_id=None,
            )
        )

    # Ordenar por número y dedupe (defensa: mismo agravio repetido).
    vistos: set[int] = set()
    unicos: list[AgravioProcesal] = []
    for a in sorted(agravios, key=lambda x: x.numero):
        if a.numero not in vistos:
            vistos.add(a.numero)
            unicos.append(a)
    return unicos


def agravios_a_texto(agravios: list[AgravioProcesal]) -> str:
    """Formatea agravios como bloque para el prompt LLM (P5).

    Similar a serializar_para_llm pero específico de agravios: cada agravio
    en su propia linea numerada. Si no hay agravios, devuelve nota de
    que no se detectaron.
    """
    if not agravios:
        return "- (No se detectaron agravios estructurados en el contexto.)"
    lineas = [f"**AGRAVIO {a.numero}:** {a.texto}" for a in agravios]
    return "\n".join(lineas)


__all__ = ["AgravioProcesal", "agravios_a_texto", "extraer_agravios"]
