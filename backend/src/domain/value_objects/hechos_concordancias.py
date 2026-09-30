"""Value object: HechosYConcordancias — output de ExtraerHechosYConcordancias (G3).

Representa la extracción estructurada de hechos procesales y concordancias
normativas desde el ContextoExpandido (fragmentos recuperados + expandidos).
El use case es pure function: recibe ContextoExpandido, devuelve este VO.

Alcance (G3, gap-analysis-asistente-v2.md):
- Hechos: segmentos de texto relevantes de los fragmentos (hechos fácticos,
  descripciones de actuaciones procesales, declaraciones, pruebas).
- Concordancias: normas jurídicas citadas (artículos, leyes, jurisprudencia)
  con referencia al fragmento origen.
- Fojas: mapeo hecho/norma -> foja(s) del expediente.
- Vicios: delega en AnalizadorVicios (G2) — se incluye resumen.
- Competencia: delega en EvaluadorCompetencia (G5) — se incluye resumen.

Diseño para que SugerirArgumentacion (G4) y el LLM (GenerarBorrador)
tengan material estructurado para redactar fundamentos de hecho y derecho.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.value_objects.resultado_competencia import ResultadoCompetencia
from src.domain.value_objects.resultado_vicios import ResultadoVicios


@dataclass(frozen=True, slots=True)
class HechoProcesal:
    """Un hecho fáctico extraído de un fragmento.

    Atributos:
        fragmento_id: ID del fragmento origen (trazabilidad).
        texto: Extracto del hecho (máx ~300 chars).
        tipo_hecho: Clasificación del hecho.
        foja_referida: Foja del expediente donde consta (si se pudo extraer).
        norma_asociada: Norma que regula o se cita en el hecho (opcional).
    """

    fragmento_id: int
    texto: str
    tipo_hecho: Literal[
        "hecho_factico",
        "actuacion_procesal",
        "declaracion_testimonial",
        "prueba_documental",
        "prueba_pericial",
        "resolucion_judicial",
        "otro",
    ]
    foja_referida: str | None
    norma_asociada: str | None


@dataclass(frozen=True, slots=True)
class ConcordanciaNormativa:
    """Una concordancia: norma jurídica citada en los fragmentos.

    Atributos:
        fragmento_id: ID del fragmento origen.
        norma_citada: Texto de la cita normativa (ej. "CPPM Art. 361").
        tipo_norma: Clasificación de la norma.
        texto_contexto: Snippet alrededor de la cita (~200 chars).
        foja_referida: Foja donde aparece la cita.
    """

    fragmento_id: int
    norma_citada: str
    tipo_norma: Literal[
        "cppm",
        "cpm",
        "cpe",
        "ley_1970",
        "lofa",
        "lojm",
        "jurisprudencia_tsjm",
        "jurisprudencia_tcp",
        "otra",
    ]
    texto_contexto: str
    foja_referida: str | None


@dataclass(frozen=True, slots=True)
class HechosYConcordancias:
    """Agregado de hechos y concordancias extraídos del contexto.

    Atributos:
        hechos: Tupla de HechoProcesal (inmutable).
        concordancias: Tupla de ConcordanciaNormativa (inmutable).
        vicios: Resumen de vicios detectados (delegado a AnalizadorVicios).
        competencia: Resumen de competencia/plazos (delegado a EvaluadorCompetencia).
        total_fragmentos_analizados: Conte para métricas.
        agravios: Agravios del recurrente (P5, apelación). Vacío en consulta.
    """

    hechos: tuple[HechoProcesal, ...]
    concordancias: tuple[ConcordanciaNormativa, ...]
    vicios: ResultadoVicios
    competencia: ResultadoCompetencia
    total_fragmentos_analizados: int
    agravios: tuple = ()

    @classmethod
    def vacio(cls) -> HechosYConcordancias:
        from src.domain.value_objects.resultado_competencia import ResultadoCompetencia
        from src.domain.value_objects.resultado_vicios import ResultadoVicios

        return cls(
            hechos=(),
            concordancias=(),
            vicios=ResultadoVicios.vacio(),
            competencia=ResultadoCompetencia.vacio(),
            total_fragmentos_analizados=0,
        )

    @property
    def hay_hechos(self) -> bool:
        return len(self.hechos) > 0

    @property
    def hay_concordancias(self) -> bool:
        return len(self.concordancias) > 0

    @property
    def hay_vicios(self) -> bool:
        return self.vicios.hay_vicios

    @property
    def hay_plazos_vencidos(self) -> bool:
        return self.competencia.hay_plazos_vencidos
