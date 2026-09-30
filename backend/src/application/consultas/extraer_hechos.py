"""Use case: ExtraerHechosYConcordancias (G3).

Extrae hechos procesales y concordancias normativas desde un
ContextoExpandido. Pure function stateless: recibe contexto, devuelve
HechosYConcordancias. Delega vicios en AnalizadorVicios (G2) y competencia
en EvaluadorCompetencia (G5).

Patrón: igual que RecuperarContexto (Sprint 5) — función async pura,
sin DI de repos, recibe todo por parámetro.
"""

from __future__ import annotations

import re

from src.domain.services.analizador_vicios import analizar_vicios
from src.domain.services.evaluador_competencia import evaluar_competencia
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.hechos_concordancias import (
    ConcordanciaNormativa,
    HechoProcesal,
    HechosYConcordancias,
)
from src.domain.value_objects.resultado_competencia import ResultadoCompetencia

# Regex para detectar citas normativas en textos jurídicos bolivianos
# BUGFIX (nombres cruzados): el CPPM es el Codigo PROCESAL Penal Militar y
# el CPM es el Codigo PENAL Militar. La regex vieja de CPPM matcheaba
# "Codigo Penal Militar" (que es el CPM) y la de CPM matcheaba "Codigo
# Procesal Militar" (nombre inexistente; el real "Codigo Procesal Penal
# Militar" nunca matcheaba). Variantes del corpus: "Codigo de
# Procedimiento Penal Militar" ( titulo formal) y OCR sin "Penal".
_RE_NORMA_CPPM = re.compile(
    r"\b(?:CPPM|C[óo]digo (?:Procesal|de Procedimiento) (?:Penal )?Militar)\s+Art\.?\s*\d+",
    re.IGNORECASE,
)
_RE_NORMA_CPM = re.compile(r"\b(?:CPM|C[óo]digo Penal Militar)\s+Art\.?\s*\d+", re.IGNORECASE)
_RE_NORMA_CPE = re.compile(r"\b(?:CPE|Constituci[óo]n Pol[íi]tica)\s+Art\.?\s*\d+", re.IGNORECASE)
_RE_NORMA_LEY1970 = re.compile(r"\bLey\s+1970\s+Art\.?\s*\d+", re.IGNORECASE)
_RE_NORMA_LOFA = re.compile(
    r"\b(?:LOFA|Ley Org[áa]nica.*Fuerzas Armadas)\s+Art\.?\s*\d+", re.IGNORECASE
)
_RE_NORMA_LOJM = re.compile(
    r"\b(?:LOJM|Ley Org[áa]nica.*Justicia Militar)\s+Art\.?\s*\d+", re.IGNORECASE
)
_RE_JURISPRUDENCIA_TSJM = re.compile(
    r"\b(?:TSJM|Tribunal Supremo Justicia Militar)\s+\d{4}[-/]\d+", re.IGNORECASE
)
_RE_JURISPRUDENCIA_TCP = re.compile(
    r"\b(?:TCP|Tribunal Constitucional Plurinacional)\s+\d{4}[-/]\d+", re.IGNORECASE
)

# Regex para detectar fojas en textos
_RE_FOJA = re.compile(r"\b(?:fojas?|fs\.?)\s*(\d+(?:\s*-\s*\d+)?(?:\s*y\s*\d+)?)", re.IGNORECASE)

# Keywords para clasificar tipo de hecho
_KEYWORDS_HECHO = {
    "hecho_factico": [
        "hecho",
        "suceso",
        "ocurrido",
        "acontecimiento",
        "los hechos",
        "la noche del",
        "el día",
        "en la madrugada",
        "lugar",
        "hora",
    ],
    "actuacion_procesal": [
        "compareció",
        "comparecencia",
        "citación",
        "notificación",
        "declaró",
        "declaración",
        "ratificó",
        "ratificación",
        "reconoció",
        "reconocimiento",
        "contestó",
        "contestación",
    ],
    "declaracion_testimonial": [
        "testigo",
        "declaró",
        "testimonio",
        "bajo juramento",
        "dijo que",
        "manifestó",
        "afirmó",
        "negó",
    ],
    "prueba_documental": [
        "documento",
        "escrito",
        "oficio",
        "certificado",
        "informe",
        "peritaje",
        "pericial",
        "dictamen pericial",
    ],
    "prueba_pericial": [
        "perito",
        "pericial",
        "dictamen pericial",
        "análisis técnico",
        "conclusión pericial",
        "informe pericial",
    ],
    "resolucion_judicial": [
        "auto",
        "sentencia",
        "resolución",
        "providencia",
        "decreto",
        "se resuelve",
        "se declara",
        "se dispone",
        "se ordena",
    ],
}

_TIPO_NORMA_MAP = [
    (_RE_NORMA_CPPM, "cppm"),
    (_RE_NORMA_CPM, "cpm"),
    (_RE_NORMA_CPE, "cpe"),
    (_RE_NORMA_LEY1970, "ley_1970"),
    (_RE_NORMA_LOFA, "lofa"),
    (_RE_NORMA_LOJM, "lojm"),
    (_RE_JURISPRUDENCIA_TSJM, "jurisprudencia_tsjm"),
    (_RE_JURISPRUDENCIA_TCP, "jurisprudencia_tcp"),
]


def _extraer_foja(texto: str) -> str | None:
    """Extrae primera foja mencionada en texto."""
    m = _RE_FOJA.search(texto)
    return m.group(1) if m else None


def _clasificar_tipo_hecho(texto: str) -> str:
    """Clasifica tipo de hecho por keywords (simple, determinista)."""
    texto_lower = texto.lower()
    for tipo, keywords in _KEYWORDS_HECHO.items():
        if any(k in texto_lower for k in keywords):
            return tipo
    return "otro"


def _extraer_hechos_de_fragmento(fragmento) -> list[HechoProcesal]:
    """Extrae hechos de un fragmento (split por oraciones largas).

    La foja se busca en el TEXTO COMPLETO del fragmento, no solo en la
    oración detectada, porque la foja suele estar en oración adyacente.
    """
    texto = fragmento.texto
    if not texto or len(texto) < 20:
        return []

    # Foja global del fragmento (se reusa para todos los hechos del fragmento)
    foja_fragmento = _extraer_foja(texto)

    # Split simple por oraciones (punto seguido de espacio + mayúscula)
    oraciones = re.split(r"\.\s+(?=[A-ZÁÉÍÓÚ])", texto)
    hechos: list[HechoProcesal] = []

    for oracion in oraciones:
        oracion = oracion.strip()
        if len(oracion) < 30 or len(oracion) > 500:
            continue

        tipo = _clasificar_tipo_hecho(oracion)
        if tipo == "otro":
            continue

        hechos.append(
            HechoProcesal(
                fragmento_id=fragmento.id,
                texto=oracion[:300],
                tipo_hecho=tipo,  # type: ignore[arg-type]
                foja_referida=foja_fragmento,
                norma_asociada=None,
            )
        )

    return hechos


def _extraer_concordancias_de_fragmento(fragmento) -> list[ConcordanciaNormativa]:
    """Extrae citas normativas de un fragmento."""
    texto = fragmento.texto
    if not texto:
        return []

    concordancias: list[ConcordanciaNormativa] = []

    for patron, tipo_norma in _TIPO_NORMA_MAP:
        for match in patron.finditer(texto):
            # Contexto ~200 chars alrededor
            ini = max(0, match.start() - 100)
            fin = min(len(texto), match.end() + 100)
            contexto = texto[ini:fin].strip()

            concordancias.append(
                ConcordanciaNormativa(
                    fragmento_id=fragmento.id,
                    norma_citada=match.group(0),
                    tipo_norma=tipo_norma,  # type: ignore[arg-type]
                    texto_contexto=contexto,
                    foja_referida=_extraer_foja(contexto),
                )
            )

    return concordancias


async def extraer_hechos_y_concordancias(
    contexto: ContextoExpandido,
    *,
    expediente_tipo_proceso: str | None = None,
    expediente_tribunal_origen: str | None = None,
    expediente_procesado_grado: str | None = None,
    expediente_created_at: object | None = None,
    obras: list | None = None,
    hoy: object | None = None,
) -> HechosYConcordancias:
    """Extrae hechos y concordancias desde ContextoExpandido.

    Args:
        contexto: ContextoExpandido con fragmentos_con_padres.
        expediente_tipo_proceso: Para EvaluadorCompetencia (opcional).
        expediente_tribunal_origen: Para EvaluadorCompetencia (opcional).
        expediente_procesado_grado: Para EvaluadorCompetencia (opcional).
        expediente_created_at: date de creación expediente (opcional).
        obras: Lista de Obra para cadena temporal plazos (opcional).
        hoy: date actual para plazos (opcional).

    Returns:
        HechosYConcordancias con hechos, concordancias, vicios, competencia.

    Notas:
        - Parámetros de competencia son opcionales: si faltan, se omite
          el chequeo de competencia (ResultadoCompetencia.vacio()).
        - AnalizadorVicios y EvaluadorCompetencia son pure functions,
          no requieren DI ni mocks.
    """
    if not contexto.fragmentos_con_padres:
        return HechosYConcordancias.vacio()

    # 1. Vicios (AnalizadorVicios G2)
    fragmentos_texto = [(f.id, f.texto) for f in contexto.fragmentos_con_padres]
    vicios = analizar_vicios(fragmentos_texto)

    # 2. Competencia (EvaluadorCompetencia G5) - solo si hay datos mínimos
    if all(
        v is not None
        for v in [
            expediente_tipo_proceso,
            expediente_tribunal_origen,
            expediente_created_at,
        ]
    ):
        from datetime import date

        competencia = evaluar_competencia(
            expediente_tipo_proceso=expediente_tipo_proceso,
            expediente_tribunal_origen=expediente_tribunal_origen,
            expediente_procesado_grado=expediente_procesado_grado or "",
            expediente_sentencia_origen=None,
            expediente_created_at=expediente_created_at,  # type: ignore[arg-type]
            obras=obras or [],
            hoy=hoy if hoy else date.today(),  # type: ignore[arg-type]
        )
    else:
        competencia = ResultadoCompetencia.vacio()

    # 3. Hechos y concordancias por fragmento
    todos_hechos: list[HechoProcesal] = []
    todas_concordancias: list[ConcordanciaNormativa] = []

    for frag in contexto.fragmentos_con_padres:
        todos_hechos.extend(_extraer_hechos_de_fragmento(frag))
        todas_concordancias.extend(_extraer_concordancias_de_fragmento(frag))

    # P5: agravios del recurrente (apelación) desde el texto del contexto.
    from src.domain.services.extraer_agravios import extraer_agravios

    agravios = extraer_agravios(list(contexto.fragmentos_con_padres))

    return HechosYConcordancias(
        hechos=tuple(todos_hechos),
        concordancias=tuple(todas_concordancias),
        vicios=vicios,
        competencia=competencia,
        total_fragmentos_analizados=len(contexto.fragmentos_con_padres),
        agravios=tuple(agravios),
    )
