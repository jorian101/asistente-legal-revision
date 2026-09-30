"""Servicio de dominio: AnalizadorVicios (Sprint 7, G2).

Detecta vicios procesales sobre el texto de fragmentos mediante regex +
heuristica. Diseado para cablearse en el ResolvedorPlantillas (G1):
cuando el LLM redacta un Auto de Vista, necesita saber si hay vicios de
nulidad para resolver el condicional
`{{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}`.

Regla arquitectonica (arquitectura.md §3.2): AnalizadorVicios es stateless
y pure function — recibe texto (no acceso a DB, no IO, no datetime.now).
Esto lo hace 100% determinista y testeable sin mocks.

Alcance explicito:
- Vicios cubiertos: indefension, falta_notificacion, plazo_vencido,
  falta_firma (detectables por patron textual).
- Vicios NO cubiertos (requieren EvaluadorCompetencia G5):
  * vencimiento de plazos contra fecha del expediente (multivariable).
  * competencia por materia / territorio / grado (grafo legal).
  * vicios de actividad probatoria (requieren logica de valoracion).

Para ambos casos, el VO ResultadoVicios.vicios estara vacio y la decision
queda en manos del ResolvedorPlantillas con su fallback actual.
"""

from __future__ import annotations

import re

from src.domain.value_objects.resultado_vicios import (
    ResultadoVicios,
    TipoVicio,
    VicioDetectado,
)

#: Snippet max length para mostrar al usuario (~100 chars alrededor del match).
_SNIPPET_RADIO = 50

#: Mapa regex por tipo de vicio. Compilados una sola vez.
#:
#: Cada entrada: (regex_compiled, norma_vulnerada_sugerida).
#: Los patrones se anclan case-insensitive pero NO con \b porque el espanol
#: usa diacriticos que rompen boundaries. match() (no search()) cuando aplica.
#:
#: ponytail: catalogo chico, mantenible. Si crece a >6 entradas, dividir en
#: modulo aparte `catalogos_vicios.py` con dataclasses por vicio.
#:
#: Nota semantica (G2 — desambiguacion):
#: - 'indefension' es solo la keyword directa 'indefension procesal'. Las
#:   manifestaciones concretas (no fue notificado, sin notificacion) son
#:   SUPUESTOS DE HECHO y se catalogan como 'falta_notificacion'. Asi cada
#:   causa tiene un solo tipo y no duplicamos detecciones.
_PATRONES_VICIO: tuple[tuple[re.Pattern[str], TipoVicio, str], ...] = (
    # Indefension: resultado procesal de no haber tenido oportunidad de
    # defenderse. Solo la keyword directa para no solapar con falta_notificacion.
    (
        re.compile(
            r"\bindefensi[oó]n(?:\s+procesal)?",
            re.IGNORECASE,
        ),
        "indefension",
        "CPPM Art. 361",
    ),
    # Falta de notificacion: el hecho puntual (no fue notificado, sin
    # notificacion, notificacion defectuosa, acta sin firma).
    (
        re.compile(
            r"\b(?:no\s+(?:fue\s+)?(?:notificado|citad[oa])(?:\s+con\s+(?:la\s+)?(?:acusaci[oó]n|resoluci[oó]n))?|"
            r"sin\s+(?:notificaci[oó]n|citaci[oó]n)|"
            r"notificaci[oó]n\s+(?:defectuosa|incompleta|nula|sin\s+firma)|"
            r"acta\s+de\s+notificaci[oó]n\s+no\s+firmada|"
            r"nulidad\s+de\s+notificaci[oó]n|"
            r"no\s+conoci[oó]\s+(?:el\s+)?proceso)",
            re.IGNORECASE,
        ),
        "falta_notificacion",
        "CPPM Arts. 161-164",
    ),
    # Plazo vencido (texto explicito). NO detecta plazos calculados contra
    # fecha del expediente; eso es EvaluadorCompetencia (G5).
    # Acepta: "plazo vencido", "vencio el plazo", "vencido el plazo".
    (
        re.compile(
            r"\b(?:plazo\s+(?:vencido|caducado|transcurrido|expirad[oa])|"
            r"fuera\s+del?\s+plazo|extempor[aá]ne[oa]d?|"  # extemporaneo/a/idad
            r"venci[oó]\s+(?:el|los?)\s+plazos?|"
            r"vencid[oa]\s+(?:el|los?)\s+plazos?)",
            re.IGNORECASE,
        ),
        "plazo_vencido",
        "CPPM Art. 105",
    ),
    # Falta de firma en una pieza procesal clave.
    (
        re.compile(
            r"\b(?:(?:falta|sin|carece(?:\s+de)?|no\s+consta)\s+firma(?:\s+del?\s+(?:actuario|secretari[oa]|"
            r"vocal|juez|a[uo]ditor))?|documento\s+no\s+firmado|"
            r"ausencia\s+de\s+firma\s+en\s+(?:el\s+)?(?:acta|auto|resoluci[oó]n))",
            re.IGNORECASE,
        ),
        "falta_firma",
        "CPPM Art. 75",
    ),
    # Plan D (D5): via procesal incongruente. El texto dice "apelacion" pero
    # se describe una sentencia absolutoria sin apelacion (regla de oro:
    # consulta; caso 3288). Heuristica textual sobre el mismo fragmento.
    (
        re.compile(
            r"\b(?:elev(?:ar|a|ad[oa])\s+(?:obrados\s+)?en\s+grado\s+de\s+"
            r"apelaci[oó]n|recurso\s+de\s+apelaci[oó]n\s+interpuest[oa])"
            r".{0,120}?"
            r"(?:absolutori[oa]|ninguna\s+de\s+las\s+partes\s+(?:apel[oó]|interpuso)|"
            r"no\s+haci[ée]ndose\s+uso\s+del\s+recurso)",
            re.IGNORECASE | re.DOTALL,
        ),
        "via_incongruente",
        "CPPM Art. 194 (consulta); regla de oro del modo",
    ),
    # Plan D (D5): fecha futura / cronologia incoherente. Detecta "de fecha
    # dd/mm/YYYY" donde el año capturado es posterior al año actual (alerta
    # textual; no computo de plazos, eso es EvaluadorCompetencia).
    (
        re.compile(
            r"\b(?:de\s+fecha|fechad[oa])\s+\d{1,2}[\-/]\d{1,2}[\-/](\d{4})",
            re.IGNORECASE,
        ),
        "foja_futura",
        "verificar cronologia del expediente",
    ),
)

# Regex para el articulo citado con su nombre entre parentesis: "Art. 125
# (Desercion)" o "Art. 178 Num. 3 (...)" o "Art. 125.-(Abandono...)".
# Acepta la abreviatura "Art." o "Arts." y la palabra completa "Artículo".
# Tolerante a guion/punto-guion/salto de linea entre el numero y el parentesis.
_RE_ARTICULO_NOMBRE = re.compile(
    r"(?:art[ií]cul[oa]s?\.?|arts?\.?)\s*"
    r"(\d+(?:\.\s*Num\.?\s*\d+)?)\s*"
    r"(?:\.?[\-–—]\s*)?\(([^)]{3,80})\)",
    re.IGNORECASE,
)


# Plan D (D5): si se provee el delito esperado, verificar que el nombre entre
# parentesis del articulo citado lo contenga (o sea sinonimo cercano). Caso
# 3352: "Art. 125 (Desercion)" pero el delito era "Abandono de Servicio".
# Solo se marca si el delito esperado es distinto al nombre del articulo y no
# hay superposicion de palabras relevantes.
def _detectar_articulo_incongruente(
    texto: str, delito_esperado: str | None
) -> list[VicioDetectado]:
    if not delito_esperado:
        return []
    delito_norm = re.sub(r"\s+", " ", delito_esperado.lower()).strip()
    palabras_delito = {p for p in re.split(r"[^a-záéíóúñ0-9]+", delito_norm) if len(p) >= 4}
    detectados: list[VicioDetectado] = []
    for m in _RE_ARTICULO_NOMBRE.finditer(texto):
        nombre = m.group(2).lower()
        palabras_nombre = {p for p in re.split(r"[^a-záéíóúñ0-9]+", nombre) if len(p) >= 4}
        # Si el delito esperado NO aparece en el nombre del articulo y el
        # nombre no comparte palabras significativas -> incongruente.
        coincide = palabras_delito & palabras_nombre
        if not coincide and delito_norm not in nombre:
            snippet = _build_snippet(texto, m.start(), m.end())
            foja = _extraer_foja(snippet)
            detectados.append(
                VicioDetectado(
                    tipo="articulo_incongruente",
                    fragmento_id=None,
                    foja_referida=foja,
                    snippet=snippet,
                    norma_vulnerada=f"Art. {m.group(1)} vs delito imputado: {delito_esperado}",
                )
            )
    return detectados


def _analizar_texto(
    texto: str,
    delito_esperado: str | None = None,
) -> list[VicioDetectado]:
    """Detecta todos los vicios en un texto. Helper privado (test directo)."""
    if not texto:
        return []

    detectados: list[VicioDetectado] = []
    for patron, tipo, norma in _PATRONES_VICIO:
        for match in patron.finditer(texto):
            # 1) Construir snippet (ventana amplia alrededor del match)
            snippet = _build_snippet(texto, match.start(), match.end())
            # 2) Buscar foja DENTRO del snippet (no del match puro)
            foja = _extraer_foja(snippet)
            detectado = VicioDetectado(
                tipo=tipo,
                fragmento_id=None,  # tests directos no tienen fragmento
                foja_referida=foja,
                snippet=snippet,
                norma_vulnerada=norma,
            )
            detectados.append(detectado)
    detectados.extend(_detectar_articulo_incongruente(texto, delito_esperado))
    return detectados


#: Regex para extraer foja(s) del snippet. Acepta "foja 23", "fs. 23",
#: "fojas 23-25", "foja 23 y 24".
_RE_FOJA = re.compile(
    r"\b(?:fojas?|fs\.?)\s*(\d+(?:\s*-\s*\d+)?(?:\s*y\s*\d+)?)",
    re.IGNORECASE,
)


def _build_snippet(texto: str, pos: int, end: int) -> str:
    """Extrae ~_SNIPPET_RADIO chars alrededor del match (limpio a boundaries).

    Args:
        texto: Texto fuente completo.
        pos: Posicion de inicio del match.
        end: Posicion de fin del match.

    Returns:
        String recortado con elipsis en los bordes si se trunca.
    """
    ini = max(0, pos - _SNIPPET_RADIO)
    fin = min(len(texto), end + _SNIPPET_RADIO)
    left = "..." if ini > 0 else ""
    right = "..." if fin < len(texto) else ""
    return f"{left}{texto[ini:fin].strip()}{right}"


def _extraer_foja(snippet: str) -> str | None:
    """Extrae la primera foja mencionada en el snippet. None si no hay.

    Busca DENTRO del snippet (no dentro del match puro), porque la foja
    suele estar cerca del vicio pero no dentro del keyword: ej. el match
    es 'indefension' pero la foja esta 10 palabras mas adelante.

    ponytail: el resultado se devuelve como string (ej. "23-25") porque
    el VO lo necesita para citar al usuario, no para operar sobre el.
    """
    match = _RE_FOJA.search(snippet)
    if match is None:
        return None
    return match.group(1)


def analizar_vicios(
    fragmentos_texto: list[tuple[int | None, str]],
    delito_esperado: str | None = None,
) -> ResultadoVicios:
    """Detecta vicios procesales en un lote de textos de fragmentos.

    Args:
        fragmentos_texto: Lista de tuplas (fragmento_id, texto). El
            fragmento_id es opcional para tests que pasan solo texto
            (se setea None). Para cada texto se ejecutan TODOS los
            patrones del catalogo y se acumulan los matches.
        delito_esperado: Delito imputado (Plan D D5). Si se provee, se
            verifica que el articulo citado corresponda al delito
            (deteccion de articulo-incongruente, caso 3352). None = no se
            verifica esa regla.

    Returns:
        ResultadoVicios con la lista inmutable de vicios detectados.
        Si nada matchea, devuelve ResultadoVicios.vacio() (NO None).

    Notas:
        - Sin DI: el servicio no necesita repos ni ports. Recibe todo.
        - Sin IO: regex pura, determinista. Misma entrada, mismo output.
        - Sin datetime.now: plazos calculados NO se detectan aca (G5).
    """
    if not fragmentos_texto:
        return ResultadoVicios.vacio()

    detectados: list[VicioDetectado] = []
    for fragmento_id, texto in fragmentos_texto:
        for vicio in _analizar_texto(texto, delito_esperado):
            # Reconstruir el VicioDetectado con fragmento_id del contexto.
            detectados.append(
                VicioDetectado(
                    tipo=vicio.tipo,
                    fragmento_id=fragmento_id,
                    foja_referida=vicio.foja_referida,
                    snippet=vicio.snippet,
                    norma_vulnerada=vicio.norma_vulnerada,
                )
            )

    return ResultadoVicios.de_lista(detectados)
