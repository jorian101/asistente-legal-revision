"""Use case: ClasificarTipoRespuesta — Fase 1 del pipeline RAG (Sprint 3).

Clasifica la consulta del usuario segun heuristicas keyword-based
(marco-practico.md Tabla 28 + §3.3). Determina:
- `tipo_respuesta`: consulta_simple | auto_vista_consulta |
  auto_vista_apelacion_incidental | dictamen_radicatoria_consulta |
  dictamen_radicatoria_apelacion.
- `filtros_metadata`: filtros de payload (abreviatura, etc.) para la busqueda.

Validacion: si tipo_respuesta != consulta_simple y expediente_id is None ->
ConsultaSinExpedienteError (las plantillas requieren expediente).

Pure domain logic: no depende de infra. Recibe la consulta + contexto minimo
y retorna la clasificacion. Testable sin mocks.
"""

from __future__ import annotations

import re

from src.domain.exceptions import (
    ConsultaSinExpedienteError,
    VarianteApelacionNoSoportadaError,
)
from src.domain.value_objects.contexto_recuperado import TipoRespuesta

# Heuristicas keyword (marco-practico.md seccion 3.3). case-insensitive.
# Orden: mas especifico a menos especifico (dictamen_radicatoria_* antes
# que auto_vista_* porque pueden coexistir con "apelacion" en la frase).
_PATRON_DICTAMEN_RADICATORIA_APELACION = re.compile(
    r"\b(dictamen\s+de\s+radicatoria\s+en\s+apelaci[óo]n"
    r"|radicatoria\s+en\s+apelaci[óo]n\s+incidental"
    r"|dictamen\s+radicatoria\s+incidental)\b",
    re.IGNORECASE,
)
_PATRON_DICTAMEN_RADICATORIA_CONSULTA = re.compile(
    r"\b(dictamen\s+de\s+radicatoria"
    r"|radicatoria\s+de\s+la\s+consulta"
    r"|dictamen\s+radicatoria\s+consulta)\b",
    re.IGNORECASE,
)
_PATRON_APELACION_INCIDENTAL = re.compile(
    r"\b(apelaci[óo]n\s+incidental|apela[çc][ií]on\s+incidental"
    r"|recurso\s+de\s+apelaci[óo]n\s+incidental)\b",
    re.IGNORECASE,
)
_PATRON_AUTO_VISTA_CONSULTA = re.compile(
    r"\b(auto\s+de\s+vista|consulta\s+de\s+oficio|vista\s+al\s+oficio)\b",
    re.IGNORECASE,
)

# Abreviaturas conocidas del corpus juridico (marco-practico.md §2).
# Texto en la consulta -> abreviatura con la que esta indexada la norma. La Ley
# 1970 esta indexada como CPP: filtrar por "Ley 1970" no matchea nada.
_ABREVIATURAS: dict[str, str] = {
    "CPE": "CPE",
    "CPM": "CPM",
    "CPPM": "CPPM",
    "LOJM": "LOJM",
    "LOFA": "LOFA",
    "CPP": "CPP",
    "Ley 1970": "CPP",
}

# Consultas que piden jurisprudencia/doctrina (Plan B — refuerzo tipo_fuente).
# Si coincide, el filtro agrega tipo_fuente='doctrina' para recuperar
# sentencias (SCP/SC/Corte IDH) además de las normas.
_PATRON_JURISPRUDENCIA = re.compile(
    r"\b(jurisprudencia|sentencia\s+constitucional|sentencia\s+plurinacional|"
    r"scp\b|precedente|ratio\s+decidendi|doctrina|motivaci[óo]n\s+constitucional|"
    r"corte\s+idh|tcp\b|cidh)\b",
    re.IGNORECASE,
)


def clasificar_tipo_respuesta(
    consulta: str,
    expediente_id: int | None,
    tipo_proceso: str | None = None,
    tipo_forzado: str | None = None,
) -> tuple[TipoRespuesta, dict[str, str]]:
    """Clasifica la consulta y retorna (tipo_respuesta, filtros_metadata).

    Args:
        consulta: Texto de la consulta del usuario.
        expediente_id: ID del expediente (None si consulta sin expediente).
        tipo_proceso: Tipo procesal del expediente (consulta,
            apelacion_incidental, apelacion_restringida). Opcional: cuando
            esta presente DESAMBIGUA la via procesal — los keywords del
            texto son solo heuristicas y un "auto de vista" pedido sobre un
            expediente de apelacion incidental debe clasificarse via
            apelacion aunque la frase no lo diga (la SAC decide la via por
            el expediente, no por como el usuario redacta).

    Returns:
        Tupla (tipo_respuesta, filtros_metadata) donde filtros_metadata es
        un dict con claves: abreviatura, tipo_fuente, expediente_id.
        El usuario_id vive en el adapter (Regla 4), no se filtra aqui.

    Raises:
        ConsultaSinExpedienteError: Si el tipo detectado requiere expediente
            (auto_vista_*, dictamen_radicatoria_*) y expediente_id es None.
        VarianteApelacionNoSoportadaError: Si el expediente es de apelacion
            restringida y se pide un tipo de otra via (no hay plantilla de
            esa variante todavia).
        tipo_forzado (T2): si pertenece al Literal TipoRespuesta, se usa
            directo tras validarlo; si inválido/desconocido, cae a auto
            con keywords (determinista).
    """

    # T2 fallback: tipo_forzado del frontend (intención explícita tipada).
    # Validación contra el Literal: desconocidos caen a auto normal.
    tipos_validos: frozenset[str] = frozenset(
        (
            "consulta_simple",
            "auto_vista_consulta",
            "auto_vista_apelacion_incidental",
            "dictamen_radicatoria_consulta",
            "dictamen_radicatoria_apelacion",
            "dictamen_fondo",
            "relacion_obrados",
        )
    )
    if tipo_forzado is not None and tipo_forzado in tipos_validos:
        tipo_f = tipo_forzado  # type: ignore[assignment]  # validado arriba
        # Revalidar precondición de expediente (igual que auto).
        if (
            tipo_f
            in (
                "auto_vista_consulta",
                "auto_vista_apelacion_incidental",
                "dictamen_radicatoria_consulta",
                "dictamen_radicatoria_apelacion",
                "dictamen_fondo",
                "relacion_obrados",
            )
            and expediente_id is None
        ):
            raise ConsultaSinExpedienteError(tipo_f)
        tipo = tipo_f  # type: ignore[assignment]
        filtros: dict[str, str] = {}
        # Filtros por tipo_forzado: solo jurisprudencia/doctrina si se pidió.
        # Los filtros de abreviatura y expediente vienen abajo igual.
    elif _PATRON_DICTAMEN_RADICATORIA_APELACION.search(consulta):
        tipo: TipoRespuesta = "dictamen_radicatoria_apelacion"
    elif _PATRON_DICTAMEN_RADICATORIA_CONSULTA.search(consulta):
        tipo = "dictamen_radicatoria_consulta"
    elif _PATRON_APELACION_INCIDENTAL.search(consulta):
        tipo = "auto_vista_apelacion_incidental"
    elif _PATRON_AUTO_VISTA_CONSULTA.search(consulta):
        tipo = "auto_vista_consulta"
    else:
        tipo = "consulta_simple"

    # Desambiguacion por via procesal del expediente (ver docstring): si el
    # texto pidio un documento de via consulta (auto de vista / radicatoria
    # de consulta) pero el expediente es apelacion incidental, la via real
    # es la del expediente. El dictamen_radicatoria_apelacion del patron ya
    # es via apelacion y no se toca.
    # Via apelacion restringida: no se remapea — TipoRespuesta no modela la
    # variante y la plantilla apelacion existente
    # (proyecto_auto_vista_apelacion) tiene la formula POR TANTO de la
    # incidental; mapearla cambiaria contenido legal sin respaldo. Se frena
    # con el guard de abajo mientras no exista plantilla propia.
    if tipo_proceso == "apelacion_incidental" and tipo in (
        "auto_vista_consulta",
        "dictamen_radicatoria_consulta",
    ):
        tipo = (
            "dictamen_radicatoria_apelacion"
            if tipo == "dictamen_radicatoria_consulta"
            else "auto_vista_apelacion_incidental"
        )

    # Guard de la via restringida: la SAC es competente (ver
    # EvaluadorCompetencia) pero no hay plantilla de esa variante, y las
    # plantillas existentes son de otro grado. Se falla con un error
    # descriptivo (422) en vez de emitir el documento de la via equivocada.
    # Los tipos agnosticos de grado (consulta_simple, dictamen_fondo,
    # relacion_obrados) siguen habilitados para expedientes restringidos.
    if tipo_proceso == "apelacion_restringida" and tipo in (
        "auto_vista_consulta",
        "auto_vista_apelacion_incidental",
        "dictamen_radicatoria_consulta",
        "dictamen_radicatoria_apelacion",
    ):
        raise VarianteApelacionNoSoportadaError(
            "El expediente es de apelación restringida y todavía no hay "
            f"plantilla para esa variante ({tipo} corresponde a otra vía). "
            "Se evita generar un documento con el grado equivocado."
        )

    if "filtros" not in locals():
        filtros: dict[str, str] = {}
    for texto, abrev in _ABREVIATURAS.items():
        if re.search(rf"\b{re.escape(texto)}\b", consulta, re.IGNORECASE):
            filtros["abreviatura"] = abrev
            break
    # Pedir jurisprudencia/doctrina NO restringe el tipo de fuente: el corpus
    # juridico siempre esta y la jurisprudencia y la doctrina llegan por su
    # propia coleccion (fan-out del HybridSearcher).
    if expediente_id is not None:
        filtros["expediente_id"] = str(expediente_id)
        # Expediente adjunto (Opcion 1: obras institucionales publicadas con autor=tribunal):
        # si hay expediente y la consulta es simple (no borrador) y no pide doctrina
        # explicita, limitar la busqueda a los obrados del caso. La senal es
        # estructural (expediente_id), no keywords "de que trata" (anti-overfitting).
        # Las normas del corpus se suman aparte (PipelineRAG._fusionar_normas_corpus).
        if tipo == "consulta_simple" and not _PATRON_JURISPRUDENCIA.search(consulta):
            filtros["solo_expediente"] = "True"

    if tipo != "consulta_simple" and expediente_id is None:
        raise ConsultaSinExpedienteError(
            f"La consulta clasificada como {tipo!r} requiere un expediente_id."
        )

    return tipo, filtros
