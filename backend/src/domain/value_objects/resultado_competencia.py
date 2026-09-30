"""Value object: ResultadoCompetencia — output del EvaluadorCompetencia (Sprint 7, G5).

Representa la evaluación de competencia y plazos para un expediente en la SAC.
El EvaluadorCompetencia es pure function stateless: recibe datos estructurados
del expediente y obras, devuelve este VO.

Regla arquitectonica (arquitectura.md §3.2): EvaluadorCompetencia es stateless
y pure function — recibe datos (no acceso a DB, no IO, no datetime.now).
Determinista y testeable sin mocks.

Alcance:
- Competencia por materia: SAC conoce apelaciones incidentales y consultas.
- Competencia por territorio: TSJM = territorio militar boliviano completo.
- Competencia por grado: oficiales (teniente a general) vs tropa (soldado a sargento).
- Plazos fatales CPPM (calculados contra fechas dadas, NO datetime.now):
  * Auto Representación: 3 días desde recepción expediente
  * Dictamen Radicatoria: 3 días desde auto representación
  * Relación Obrados: 3 días desde sorteo
  * Dictamen Fondo: 3 días desde relación obrados
  * Proyecto Auto Vista: 48h desde dictamen fondo
  * Audiencia: 48h desde proyecto auto vista

Fuera de alcance (requieren lógica judicial humana, no automatizable):
- Excepciones de incompetencia por conexidad
- Inhibiciones / recusaciones
- Competencia por razón de cuantía (no aplica en penal militar)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TipoProceso = Literal["consulta", "apelacion_incidental"]
GradoMilitar = Literal[
    "general",
    "coronel",
    "teniente_coronel",
    "mayor",
    "capitan",
    "teniente",
    "subteniente",
    "sargento_primero",
    "sargento",
    "cabo",
    "soldado",
]
CompetenciaMateria = Literal["competente", "incompetente", "dudosa"]
CompetenciaTerritorio = Literal["competente", "incompetente"]
CompetenciaGrado = Literal["competente", "incompetente"]
PlazoEstado = Literal["dentro_plazo", "vencido", "critico", "no_aplica"]


@dataclass(frozen=True, slots=True)
class ChequeoCompetencia:
    """Resultado de un chequeo individual de competencia."""

    criterio: Literal["materia", "territorio", "grado"]
    estado: CompetenciaMateria | CompetenciaTerritorio | CompetenciaGrado
    detalle: str
    norma: str | None = None


@dataclass(frozen=True, slots=True)
class ChequeoPlazo:
    """Resultado de verificación de un plazo fatal."""

    etapa: Literal[
        "auto_representacion",
        "dictamen_radicatoria",
        "relacion_obrados",
        "dictamen_fondo",
        "proyecto_auto_vista",
        "audiencia",
    ]
    estado: PlazoEstado
    dias_transcurridos: int | None
    dias_limite: int
    fecha_inicio: str | None = None
    detalle: str = ""


@dataclass(frozen=True, slots=True)
class ResultadoCompetencia:
    """Agregado de competencia y plazos para un expediente."""

    # Competencia
    chequeos_competencia: tuple[ChequeoCompetencia, ...]
    competencia_global: CompetenciaMateria
    # Plazos
    chequeos_plazos: tuple[ChequeoPlazo, ...]
    hay_plazos_vencidos: bool
    hay_plazos_criticos: bool

    @classmethod
    def vacio(cls) -> ResultadoCompetencia:
        return cls(
            chequeos_competencia=(),
            competencia_global="competente",
            chequeos_plazos=(),
            hay_plazos_vencidos=False,
            hay_plazos_criticos=False,
        )

    @classmethod
    def de_listas(
        cls,
        chequeos_competencia: list[ChequeoCompetencia],
        chequeos_plazos: list[ChequeoPlazo],
    ) -> ResultadoCompetencia:
        # Competencia global: si alguno es incompetente -> incompetente
        # si alguno dudosa y ninguno incompetente -> dudosa
        # else -> competente
        comp_estados = [c.estado for c in chequeos_competencia]
        if "incompetente" in comp_estados:
            global_comp = "incompetente"
        elif "dudosa" in comp_estados:
            global_comp = "dudosa"
        else:
            global_comp = "competente"

        hay_vencidos = any(c.estado == "vencido" for c in chequeos_plazos)
        hay_criticos = any(c.estado == "critico" for c in chequeos_plazos)

        return cls(
            chequeos_competencia=tuple(chequeos_competencia),
            competencia_global=global_comp,
            chequeos_plazos=tuple(chequeos_plazos),
            hay_plazos_vencidos=hay_vencidos,
            hay_plazos_criticos=hay_criticos,
        )
