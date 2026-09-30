"""Value object: ResultadoVicios — output del AnalizadorVicios (Sprint 7, G2).

Representa el resultado de detectar vicios procesales sobre el texto de los
fragmentos recuperados por el pipeline RAG. El AnalizadorVicios es una pure
function stateless (ver domain/services/analizador_vicios.py): recibe texto,
devuelve instancias de este VO.

Alcance (arquitectura.md §3.2 lines 87 y 480):
- Solo vicios detectables por patron textual (regex + heuristica simple).
- Vicios que requieren inferencia multivariable (plazos calculados contra
  fechas del expediente, competencia por materia/grafo) los resuelve
  EvaluadorCompetencia (G5), NO este servicio.

Catologo de vicios cubiertos (CPPM):
- indefension: frases como "no fue notificado", "se le indefenso".
- falta_notificacion: "sin notificacion", "no se notifico".
- plazo_vencido: "plazo vencido", "plazo transcurrido", "fuera de plazo".
- falta_firma: "sin firma", "falta firma", "no firmado".

Plan D (D5, criterio del Vocal — verificacion-consistencia):
- articulo_incongruente: el articulo citado no corresponde al delito imputado
  (caso 3352: "Art. 125 (Desercion)" vs "Abandono de Servicio").
- via_incongruente: el oficio dice "apelacion" pero la sentencia es absolutoria
  y nadie apelo (regla de oro: consulta; caso 3288).
- foja_futura: un actuado con fecha posterior a la relacion de obrados o
  inconsistencia cronologica evidente (caso 3288).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TipoVicio = Literal[
    "indefension",
    "falta_notificacion",
    "plazo_vencido",
    "falta_firma",
    "articulo_incongruente",
    "via_incongruente",
    "foja_futura",
]


@dataclass(frozen=True, slots=True)
class VicioDetectado:
    """Un vicio procesal individual detectado en un fragmento.

    Atributos:
        tipo: Categoria del vicio (ver TipoVicio).
        fragmento_id: ID del fragmento donde se detecto (para trazabilidad).
            None si el analisis fue sobre texto suelto (test directo).
        foja_referida: Foja citada en el snippet si el patron la extrae
            (ej. "foja 23" -> "23"). None si no se pudo extraer.
        snippet: Extracto del texto donde se detecto el vicio (~100 chars
            alrededor del match para contexto humano).
        norma_vulnerada: Referencia normativa sugerida (ej. "CPPM Art. 361"
            para indefension). None si no hay asociacion clara.
    """

    tipo: TipoVicio
    fragmento_id: int | None
    foja_referida: str | None
    snippet: str
    norma_vulnerada: str | None


@dataclass(frozen=True, slots=True)
class ResultadoVicios:
    """Agregado de vicios detectados sobre un conjunto de fragmentos.

    Atributos:
        vicios: Tupla de VicioDetectado. Inmutable por contrato del VO.
        total: Cantidad de vicios (len(vicios) cacheado para no recalcular).
    """

    vicios: tuple[VicioDetectado, ...]
    total: int

    @classmethod
    def vacio(cls) -> ResultadoVicios:
        """Resultado sin vicios: para casos base / tests negativos."""
        return cls(vicios=(), total=0)

    @classmethod
    def de_lista(cls, vicios: list[VicioDetectado]) -> ResultadoVicios:
        """Constructor desde lista mutable (convierte a tupla inmutable)."""
        return cls(vicios=tuple(vicios), total=len(vicios))

    @property
    def hay_vicios(self) -> bool:
        """True si se detecto al menos un vicio (atajo para condicionales)."""
        return self.total > 0
