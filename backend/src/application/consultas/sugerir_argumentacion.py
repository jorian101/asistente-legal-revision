"""Value object: SugerenciaArgumentacion — output de SugerirArgumentacion (G4).

Representa una sugerencia estructurada de argumentación jurídica para un
tipo de respuesta específico (auto_vista, dictamen_radicatoria, etc.).
El use case SugerirArgumentacion usa HechosYConcordancias (G3) y
genera bloques de argumentación listos para usar en plantillas.

Alcance (G4, gap-analysis-asistente-v2.md):
- Fundamentos de hecho: selección de hechos relevantes por tipo de respuesta.
- Fundamentos de derecho: concordancias normativas agrupadas por tema.
- Vicios procesales: alertas de vicios detectados (G2) para sanamiento.
- Competencia/plazos: alertas de EvaluadorCompetencia (G5) para dictamen radicatoria.
- Citas de fojas: referencias precisas para cada argumento.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.value_objects.hechos_concordancias import (
    ConcordanciaNormativa,
    HechoProcesal,
    HechosYConcordancias,
)


@dataclass(frozen=True, slots=True)
class BloqueArgumentacion:
    """Un bloque de argumentación jurídica (hecho + norma + análisis)."""

    titulo: str
    tipo: Literal["hecho", "derecho", "vicio", "competencia", "plazo"]
    contenido: str
    fojas_referidas: tuple[str, ...]
    normas_citadas: tuple[str, ...]
    prioridad: Literal["alta", "media", "baja"]


@dataclass(frozen=True, slots=True)
class SugerenciaArgumentacion:
    """Sugerencia completa de argumentación para un tipo de respuesta."""

    tipo_respuesta: Literal[
        "auto_vista_consulta",
        "auto_vista_apelacion_incidental",
        "dictamen_radicatoria_consulta",
        "dictamen_radicatoria_apelacion",
    ]
    fundamentos_hecho: tuple[BloqueArgumentacion, ...]
    fundamentos_derecho: tuple[BloqueArgumentacion, ...]
    vicios_sanear: tuple[BloqueArgumentacion, ...]
    alertas_competencia: tuple[BloqueArgumentacion, ...]
    alertas_plazos: tuple[BloqueArgumentacion, ...]
    resumen_ejecutivo: str
    agravios: tuple = ()

    @classmethod
    def vacia(cls, tipo_respuesta: str) -> SugerenciaArgumentacion:
        return cls(
            tipo_respuesta=tipo_respuesta,  # type: ignore[arg-type]
            fundamentos_hecho=(),
            fundamentos_derecho=(),
            vicios_sanear=(),
            alertas_competencia=(),
            alertas_plazos=(),
            resumen_ejecutivo="Sin datos suficientes para generar sugerencia.",
        )

    @property
    def total_bloques(self) -> int:
        return (
            len(self.fundamentos_hecho)
            + len(self.fundamentos_derecho)
            + len(self.vicios_sanear)
            + len(self.alertas_competencia)
            + len(self.alertas_plazos)
        )


def sugerir_argumentacion(
    hechos_y_concordancias: HechosYConcordancias,
    tipo_respuesta: str,
) -> SugerenciaArgumentacion:
    """Genera sugerencia de argumentación desde HechosYConcordancias (G4).

    Pure function: recibe HechosYConcordancias (output G3) + tipo_respuesta,
    devuelve SugerenciaArgumentacion con bloques estructurados.

    Lógica por tipo_respuesta:
    - auto_vista_consulta: hechos fácticos + actuaciones + vicios sanear +
      concordancias CPPM/CPE + alertas plazos 48h
    - auto_vista_apelacion_incidental: hechos + declaraciones testif. +
      concordancias CPM/Ley1970 + vicios + alertas competencia
    - dictamen_radicatoria_*: competencia (prioridad alta) + vicios +
      concordancias Ley 1970 Art. 3 + plazos 3 días

    ponytail: lógica simple por reglas, sin LLM. El LLM (GenerarBorrador)
    usa estos bloques como input estructurado para redactar.
    """
    if hechos_y_concordancias.total_fragmentos_analizados == 0:
        return SugerenciaArgumentacion.vacia(tipo_respuesta)

    fundamentos_hecho = _bloques_hecho(hechos_y_concordancias, tipo_respuesta)
    fundamentos_derecho = _bloques_derecho(hechos_y_concordancias, tipo_respuesta)
    vicios_sanear = _bloques_vicios(hechos_y_concordancias)
    alertas_competencia = _bloques_competencia(hechos_y_concordancias)
    alertas_plazos = _bloques_plazos(hechos_y_concordancias)
    resumen = _resumen_ejecutivo(
        tipo_respuesta,
        fundamentos_hecho,
        fundamentos_derecho,
        vicios_sanear,
        alertas_competencia,
        alertas_plazos,
    )

    return SugerenciaArgumentacion(
        tipo_respuesta=tipo_respuesta,  # type: ignore[arg-type]
        fundamentos_hecho=tuple(fundamentos_hecho),
        fundamentos_derecho=tuple(fundamentos_derecho),
        vicios_sanear=tuple(vicios_sanear),
        alertas_competencia=tuple(alertas_competencia),
        alertas_plazos=tuple(alertas_plazos),
        resumen_ejecutivo=resumen,
        agravios=hechos_y_concordancias.agravios,
    )


def _bloques_hecho(
    hechos_y_concordancias: HechosYConcordancias,
    tipo_respuesta: str,
) -> list[BloqueArgumentacion]:
    """Fundamentos de hecho: agrupa por tipo y prioriza según la respuesta."""
    hechos_por_tipo: dict[str, list[HechoProcesal]] = {}
    for h in hechos_y_concordancias.hechos:
        hechos_por_tipo.setdefault(h.tipo_hecho, []).append(h)

    prioridad_hechos = {
        "auto_vista_consulta": ["hecho_factico", "actuacion_procesal", "resolucion_judicial"],
        "auto_vista_apelacion_incidental": [
            "hecho_factico",
            "declaracion_testimonial",
            "actuacion_procesal",
        ],
        "dictamen_radicatoria_consulta": ["actuacion_procesal", "resolucion_judicial"],
        "dictamen_radicatoria_apelacion": ["actuacion_procesal", "resolucion_judicial"],
    }.get(tipo_respuesta, ["hecho_factico", "actuacion_procesal"])

    bloques: list[BloqueArgumentacion] = []
    for tipo in prioridad_hechos:
        for h in hechos_por_tipo.get(tipo, [])[:3]:  # máx 3 por tipo
            fojas = (h.foja_referida,) if h.foja_referida else ()
            bloques.append(
                BloqueArgumentacion(
                    titulo=f"Hecho: {tipo.replace('_', ' ').title()}",
                    tipo="hecho",
                    contenido=h.texto,
                    fojas_referidas=fojas,
                    normas_citadas=(h.norma_asociada,) if h.norma_asociada else (),
                    prioridad="alta",
                )
            )
    return bloques


def _bloques_derecho(
    hechos_y_concordancias: HechosYConcordancias,
    tipo_respuesta: str,
) -> list[BloqueArgumentacion]:
    """Fundamentos de derecho: agrupa concordancias por tipo de norma."""
    normas_por_tipo: dict[str, list[ConcordanciaNormativa]] = {}
    for c in hechos_y_concordancias.concordancias:
        normas_por_tipo.setdefault(c.tipo_norma, []).append(c)

    prioridad_normas = {
        "auto_vista_consulta": ["cppm", "cpe", "jurisprudencia_tsjm"],
        "auto_vista_apelacion_incidental": ["cpm", "ley_1970", "jurisprudencia_tsjm"],
        "dictamen_radicatoria_consulta": ["ley_1970", "cppm"],
        "dictamen_radicatoria_apelacion": ["ley_1970", "cpm"],
    }.get(tipo_respuesta, ["cppm", "cpe"])

    bloques: list[BloqueArgumentacion] = []
    for tn in prioridad_normas:
        for c in normas_por_tipo.get(tn, [])[:3]:
            fojas = (c.foja_referida,) if c.foja_referida else ()
            bloques.append(
                BloqueArgumentacion(
                    titulo=f"Norma: {c.norma_citada}",
                    tipo="derecho",
                    contenido=c.texto_contexto,
                    fojas_referidas=fojas,
                    normas_citadas=(c.norma_citada,),
                    prioridad="alta",
                )
            )
    return bloques


def _bloques_vicios(
    hechos_y_concordancias: HechosYConcordancias,
) -> list[BloqueArgumentacion]:
    """Vicios a sanar detectados por el analizador de vicios."""
    return [
        BloqueArgumentacion(
            titulo=f"Vicio: {v.tipo.replace('_', ' ').title()}",
            tipo="vicio",
            contenido=v.snippet,
            fojas_referidas=(v.foja_referida,) if v.foja_referida else (),
            normas_citadas=(v.norma_vulnerada,) if v.norma_vulnerada else (),
            prioridad="alta",
        )
        for v in hechos_y_concordancias.vicios.vicios
    ]


def _bloques_competencia(
    hechos_y_concordancias: HechosYConcordancias,
) -> list[BloqueArgumentacion]:
    """Alertas de competencia (solo si la competencia global no es competente)."""
    if hechos_y_concordancias.competencia.competencia_global == "competente":
        return []
    return [
        BloqueArgumentacion(
            titulo=f"Competencia {ck.criterio}: {ck.estado}",
            tipo="competencia",
            contenido=ck.detalle,
            fojas_referidas=(),
            normas_citadas=(ck.norma,) if ck.norma else (),
            prioridad="alta",
        )
        for ck in hechos_y_concordancias.competencia.chequeos_competencia
        if ck.estado != "competente"
    ]


def _bloques_plazos(
    hechos_y_concordancias: HechosYConcordancias,
) -> list[BloqueArgumentacion]:
    """Alertas de plazos vencidos o críticos."""
    return [
        BloqueArgumentacion(
            titulo=f"Plazo {cp.etapa.replace('_', ' ').title()}: {cp.estado}",
            tipo="plazo",
            contenido=cp.detalle,
            fojas_referidas=(),
            normas_citadas=(),
            prioridad="alta" if cp.estado == "vencido" else "media",
        )
        for cp in hechos_y_concordancias.competencia.chequeos_plazos
        if cp.estado in ("vencido", "critico")
    ]


def _resumen_ejecutivo(
    tipo_respuesta: str,
    fundamentos_hecho: list[BloqueArgumentacion],
    fundamentos_derecho: list[BloqueArgumentacion],
    vicios_sanear: list[BloqueArgumentacion],
    alertas_competencia: list[BloqueArgumentacion],
    alertas_plazos: list[BloqueArgumentacion],
) -> str:
    """Resumen ejecutivo con conteos de cada categoría."""
    resumen_partes = []
    if fundamentos_hecho:
        resumen_partes.append(f"{len(fundamentos_hecho)} fundamentos de hecho")
    if fundamentos_derecho:
        resumen_partes.append(f"{len(fundamentos_derecho)} concordancias normativas")
    if vicios_sanear:
        resumen_partes.append(f"{len(vicios_sanear)} vicios a sanear")
    if alertas_competencia:
        resumen_partes.append(f"{len(alertas_competencia)} alertas de competencia")
    if alertas_plazos:
        resumen_partes.append(f"{len(alertas_plazos)} alertas de plazos")

    if not resumen_partes:
        return "Sin elementos relevantes detectados."
    cuerpo = "; ".join(resumen_partes)
    return f"Sugerencia para {tipo_respuesta.replace('_', ' ')}: {cuerpo}. "


def serializar_para_llm(sugerencia: SugerenciaArgumentacion) -> str:
    """Formatea la sugerencia como bloque estructurado para el prompt LLM (P4).

    Convierte los bloques (hechos, derecho, vicios) en texto con fojas y
    normas citadas, y agrega una instruccion anti-alucinacion: el LLM solo
    debe usar las fojas aqui listadas (verificadas del contexto), nunca
    inventar otras. La cadena se inyecta en el slot {{sugerencia_argumentacion}}
    de la plantilla junto con {{contexto_expandido}}.

    Si no hay bloques, devuelve una nota de que no hay hitos estructurados
    (el LLM debe basarse solo en el contexto y no completar fojas).
    """
    lineas: list[str] = [
        "Datos verificados del expediente (extraccion estructurada del contexto):",
        "Regla: SOLO cita las fojas listadas aqui. Si una foja no aparece, "
        "NO la inventes y omite la referencia a foja (no escribas frases de "
        "relleno ni marcadores de dato faltante).",
    ]

    # P5 + Plan D (D5b): agravios del recurrente (apelación) — se listan como
    # bloques numerados individuales para que el LLM los RESUELVA uno por uno
    # en apartados propios (patrón del 3145: CONSIDERANDO por agravio). Sin
    # omisión ni exceso (congruencia, Art. 115.II CPE).
    if sugerencia.agravios:
        from src.domain.services.extraer_agravios import agravios_a_texto

        lineas.append("AGRAVIOS DEL RECURRENTE (responder CADA UNO, sin omision ni exceso):")
        lineas.append(agravios_a_texto(list(sugerencia.agravios)))
        lineas.append("")
        lineas.append(
            "INSTRUCCION DE DESGLOSE: en apelacion, cada agravio debe analizarse "
            "y resolverse en un apartado propio del Considerando de analisis "
            "(CONSIDERANDO por agravio o sub-seccion numerada). No omitir ninguno."
        )
        lineas.append("")

    bloques: list[BloqueArgumentacion] = [
        *sugerencia.fundamentos_hecho,
        *sugerencia.fundamentos_derecho,
        *sugerencia.vicios_sanear,
    ]
    if not bloques:
        nota = "- (Sin hitos estructurados: basate solo en el contexto, sin inventar fojas.)"
        lineas.append(nota)
        return "\n".join(lineas)

    for b in bloques:
        foja = ", ".join(b.fojas_referidas) if b.fojas_referidas else "sin foja en el fragmento"
        normas = ", ".join(b.normas_citadas) if b.normas_citadas else "-"
        lineas.append(f"- [{b.titulo}] foja: {foja} | norma: {normas}\n  {b.contenido[:200]}")

    return "\n".join(lineas)


async def ejecutar_sugerencia(
    contexto: object,
    *,
    usuario_id: int,
    expediente_repo: object | None = None,
    obra_repo: object | None = None,
) -> SugerenciaArgumentacion:
    """Orquesta contexto RAG -> ExtraerHechosYConcordancias -> sugerir_argumentacion.

    Compartido entre GenerarBorrador (Fase 5) y el endpoint HTTP
    /consultas/sugerir-argumentacion (Fase 5b). NO corre el pipeline RAG:
    recibe el ContextoExpandido ya recuperado para evitar doble RAG.

    Args:
        contexto: ContextoExpandido (o ContextoRecuperado upcasteable).
        usuario_id: ID del usuario autenticado (Regla 4 — filtro obras).
        expediente_repo: Opcional — enriquece competencia con expediente real.
        obra_repo: Opcional — lista obras del expediente para plazos.

    Returns:
        SugerenciaArgumentacion (puede estar vacía si no hay fragmentos).
    """
    from src.application.consultas.extraer_hechos import extraer_hechos_y_concordancias
    from src.domain.value_objects.contexto_expandido import ContextoExpandido
    from src.domain.value_objects.contexto_recuperado import ContextoRecuperado

    if isinstance(contexto, ContextoRecuperado) and not isinstance(contexto, ContextoExpandido):
        contexto = ContextoExpandido(
            fragmentos_con_padres=contexto.fragmentos,
            scores=contexto.scores,
            query_original=contexto.query_original,
            tipo_respuesta=contexto.tipo_respuesta,
            expediente_id=contexto.expediente_id,
            breadcrumbs=(),
            trazabilidad=None,
            latencia_ms=contexto.latencia_ms,
        )

    expediente = None
    obras: list = []
    if contexto.expediente_id is not None and expediente_repo is not None:
        expediente = await expediente_repo.obtener(contexto.expediente_id)
    if contexto.expediente_id is not None and obra_repo is not None:
        obras = await obra_repo.listar_por_expediente(contexto.expediente_id, usuario_id)

    hc = await extraer_hechos_y_concordancias(
        contexto,
        expediente_tipo_proceso=expediente.tipo_proceso if expediente else None,
        expediente_tribunal_origen=expediente.tribunal_origen if expediente else None,
        expediente_procesado_grado=expediente.procesado_grado if expediente else None,
        expediente_created_at=(
            expediente.created_at.date() if expediente and expediente.created_at else None
        ),
        obras=obras,
        hoy=None,
    )
    return sugerir_argumentacion(hc, contexto.tipo_respuesta)
