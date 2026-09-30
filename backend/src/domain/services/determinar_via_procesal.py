"""Domain service: DeterminarViaProcesal — regla de oro del modo (P1.1).

Pure domain logic: decide la via procesal correcta de un expediente TSJM a
partir de senales procesales (sentencia, recurso, rotulo del oficio), NO de la
consulta keyword del usuario. Sin I/O, sin DI: todas las entradas son
parametros; no depende de datetime ni infraestructura.

Regla de oro del modo (vault: flujo-procesal-consulta.md, caso 3288):
- Sentencia absolutoria + ausencia de recurso -> CONSULTA de oficio,
  aunque el oficio de elevacion diga "apelacion" (error real de rotulacion
  corregido en el caso 3288: oficio N 344/2025 decia 'apelacion', fue consulta).
- Recurso de parte contra auto interlocutorio -> APELACION INCIDENTAL.
- Recurso de parte contra sentencia -> APELACION RESTRINGIDA.

La rotulacion del oficio es la senal de MENOR autoridad: se usa solo cuando
las demas no alcanzan a decidir, y nunca para sobreescribir sentencia+recurso.

Salidas (ViaProcesal):
    consulta_oficio | apelacion_incidental | apelacion_restringida |
    sin_datos_suficientes
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ViaProcesal(StrEnum):
    """Via procesal determinada para el expediente."""

    CONSULTA_OFICIO = "consulta_oficio"
    APELACION_INCIDENTAL = "apelacion_incidental"
    APELACION_RESTRINGIDA = "apelacion_restringida"
    SIN_DATOS = "sin_datos_suficientes"


class SentidoSentencia(StrEnum):
    """Sentido del fallo de la sentencia/resolucion de origen."""

    ABSOLUTORIA = "absolutoria"
    CONDENATORIA = "condenatoria"
    DESCONOCIDO = "desconocido"


class TipoRecurso(StrEnum):
    """Tipo de recurso presentado por las partes."""

    APELACION_INCIDENTAL = "apelacion_incidental"
    APELACION_RESTRINGIDA = "apelacion_restringida"
    NINGUNO = "ninguno"


class RotuloOficio(StrEnum):
    """Lo que dice el oficio de elevacion (autoridad MENOR)."""

    CONSULTA = "consulta"
    APELACION = "apelacion"
    SIN_ROTULO = "sin_rotulo"


@dataclass(frozen=True, slots=True)
class SenalesExpediente:
    """Senales procesales del expediente para decidir la via.

    Args:
        sentido_sentencia: Sentido del fallo del inferior (absolutoria,
            condenatoria, desconocido).
        tipo_recurso: Recurso presentado por las partes (ninguno si no hay).
        rotulo_oficio: Rotulacion del oficio de elevacion (autoridad menor).
    """

    sentido_sentencia: SentidoSentencia = SentidoSentencia.DESCONOCIDO
    tipo_recurso: TipoRecurso = TipoRecurso.NINGUNO
    rotulo_oficio: RotuloOficio = RotuloOficio.SIN_ROTULO


def determinar_via_procesal(senales: SenalesExpediente) -> ViaProcesal:
    """Determina la via procesal del expediente (regla de oro del modo).

    Precedencia de senales (de mayor a menor autoridad):
    1. Recurso presentado -> define apelacion (incidental o restringida).
    2. Sentencia absolutoria sin recurso -> consulta de oficio.
    3. Rotulo del oficio -> ultimo recurso, NUNCA sobreescribe 1 y 2.
    4. Sin datos suficientes -> ViaProcesal.SIN_DATOS (no inventar).

    Raises:
        ValueError: si una senal llega con tipo inesperado (defensivo).
    """
    if not isinstance(senales.sentido_sentencia, SentidoSentencia):
        raise ValueError("sentido_sentencia debe ser SentidoSentencia")
    if not isinstance(senales.tipo_recurso, TipoRecurso):
        raise ValueError("tipo_recurso debe ser TipoRecurso")
    if not isinstance(senales.rotulo_oficio, RotuloOficio):
        raise ValueError("rotulo_oficio debe ser RotuloOficio")

    # 1. Recurso presentado manda (apelacion).
    if senales.tipo_recurso == TipoRecurso.APELACION_INCIDENTAL:
        return ViaProcesal.APELACION_INCIDENTAL
    if senales.tipo_recurso == TipoRecurso.APELACION_RESTRINGIDA:
        return ViaProcesal.APELACION_RESTRINGIDA

    # 2. Sentencia absolutoria + sin recurso -> consulta (regla de oro).
    if senales.sentido_sentencia == SentidoSentencia.ABSOLUTORIA:
        return ViaProcesal.CONSULTA_OFICIO

    # 3. Rotulo del oficio como ultimo recurso (no sobreescribe 1 y 2).
    if senales.rotulo_oficio == RotuloOficio.CONSULTA:
        return ViaProcesal.CONSULTA_OFICIO
    if senales.rotulo_oficio == RotuloOficio.APELACION:
        return ViaProcesal.APELACION_RESTRINGIDA

    # 4. Sin datos suficientes: no inventar.
    return ViaProcesal.SIN_DATOS


__all__ = [
    "RotuloOficio",
    "SenalesExpediente",
    "SentidoSentencia",
    "TipoRecurso",
    "ViaProcesal",
    "determinar_via_procesal",
]
