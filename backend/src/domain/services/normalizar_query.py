"""Domain service: NormalizarQuery — limpia ruido lingüístico del inicio de la consulta.

Pure domain logic: recibe el texto de la consulta del usuario y retorna una
versión limpia para usar SOLO en la búsqueda (embedding). No modifica el
texto visible al usuario ni el que recibe el LLM.

Motivo (bug sala): saludos ("hola", "ola"), muletillas ("por favor") e
interrogativas vacías ("cual es", "de que trata") al inicio de la frase
ensucian el embedding denso y desplazan los fragmentos relevantes fuera del
top-k final. Ej. "hola cual es el prinincipio del debido proceso" dejaba el
Art. 115 CPE (debido proceso) fuera del top 7; sin saludo entraba.

Capa A (anti-overfit): los typos de términos jurídicos se corrigen por
edit-distance contra el VOCABULARIO del corpus (Capa A), no con un
diccionario fijo. Si se provee `vocabulario`, cada token desconocido se
compara (Levenshtein con banda, max dist 2) contra candidatos de longitud
similar; solo se corrige si hay un match único claro. Sin vocabulario se
usa el dict mínimo como fallback (compat/tests).

Solo opera sobre el PREFIJO de la frase para saludos/muletillas, pero la
corrección de typos recorre TODOS los tokens (un typo puede estar en
cualquier posición). Si tras la limpieza no queda texto útil, retorna el
original (defensivo).
"""

from __future__ import annotations

import re
from functools import lru_cache

# Saludos y aperturas conversacionales (case-insensitive, al inicio exacto).
_PREFIJOS_SALUDO = re.compile(
    r"^\s*(?:"
    r"hola+|ola+"
    r"|buenas+\s*(?:tardes|noches|d[ií]as|dias)?"
    r"|buen[oa]s?\s*d[ií]as"
    r"|que\s*tal|qu[eé]\s*tal|hey|saludos"
    r")\s*[,\s]*",
    re.IGNORECASE,
)

# Muletillas/interrogativas vacías que NO aportan contenido semántico.
# Son prefijos de pregunta que el LLM entiende igual sin ellas.
_PREFIJOS_MULETILLA = re.compile(
    r"^\s*(?:"
    r"por\s*favor"
    r"|me\s*podr[ií]as\s*decir|me\s*puedes\s*decir|me\s*dir[ií]as"
    r"|podr[ií]as\s*decirme|puedes\s*decirme|me\s*ayudas?\s*a"
    r"|quisiera\s*saber|querr[ií]a\s*saber|necesito\s*saber|quiero\s*saber"
    r"|sab[ée]s?\s*(?:si|algo)?"
    r")\s*[,\s]*",
    re.IGNORECASE,
)

# Interrogativas vacías "cual es el X", "que es un X", "de que trata X".
# Consume el prefijo completo incluyendo articulo, dejando el sustantivo.
_PREFIJO_INTERROGATIVA = re.compile(
    r"^\s*(?:"
    r"cu[aá]l\s+(?:es|ser[ií]a|fue)"
    r"|qu[eé]\s+(?:es|ser[ií]a|fue|significa)"
    r"|d[eé]\s+qu[eé]\s+(?:trata|habla)"
    r"|en\s+qu[eé]\s+consiste|qu[eé]\s+son|c[uó]al\s+son"
    r"|c[oó]mo\s+(?:se|funciona|esta|est[aá])"
    r"|cu[aá]ndo|d[oó]nde|qui[eé]n|para\s+qu[eé]"
    r")\s+"
    r"(?:el|la|los|las|un|una|unos|unas|lo|es|son)?\s*",
    re.IGNORECASE,
)

# Imperativos de apertura ("dime sobre", "explícame", "háblame de") y la
# referencia genérica "el artículo (de|del|de la)" SIN número: no aportan
# contenido semántico y en BM25 "articulo" pesa como una palabra clave.
# "el artículo 115" conserva el número (dato de búsqueda), por eso el
# lookahead niega un dígito.
_PREFIJO_IMPERATIVO = re.compile(
    r"^\s*(?:"
    r"d[ií]me(?:lo)?|expl[ií]came(?:lo)?|cu[eé]ntame|h[aá]blame|expl[ií]ca(?:me)?(?:lo)?"
    r"|(?:quiero|necesito)\s+que\s+me\s+expliques"
    r")\s*(?:(?:sobre|acerca\s+de|de)\s+)?"
    r"(?:(?:el|la|los|las)\s+)?"
    r"(?:art[ií]culos?\s+(?!\d)(?:del?\s+(?:la\s+|los\s+|las\s+)?)?)?",
    re.IGNORECASE,
)
_SUFIJO_IMPERATIVO = re.compile(
    r"[\s,;.]*(?:por\s+favor[\s,]*)?expl[ií]ca(?:me)?(?:lo|la|los|las)?\s*[?!.]*\s*$",
    re.IGNORECASE,
)

_MAX_PASADAS = 3

# Fallback sin vocabulario: variantes tipicas de terminos juridicos.
# Capa A lo reemplaza por edit-distance contra el corpus cuando hay
# vocabulario; este dict solo cubre tests y calls sin vocabulario.
_TYPOS_JURIDICOS: dict[str, str] = {
    "prinincipio": "principio",
    "pricipio": "principio",
    "princípio": "principio",
    "proseso": "proceso",
    "proseco": "proceso",
    "prescricion": "prescripcion",
    "prescripsion": "prescripcion",
    "jusgado": "juzgado",
    "apelasion": "apelacion",
    "sentensia": "sentencia",
    "recursso": "recurso",
    "competensia": "competencia",
}
_TYPOS_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _TYPOS_JURIDICOS) + r")\b",
    re.IGNORECASE,
)

# Distancia maxima aceptada para considerar que un token es un typo.
_MAX_EDIT_DIST = 2
# Tokens mas cortos que esto no se corrigen (falsos positivos en nombres).
_MIN_TOKEN_LEN = 4


@lru_cache(maxsize=4)
def _indice_por_longitud(
    vocabulario: frozenset[str],
) -> tuple[dict[int, frozenset[str]], dict[tuple[int, str], frozenset[str]]]:
    """Indexa el vocabulario por longitud y por (longitud, primer char).

    Cacheado (el corpus cambia raro). Los buckets por (longitud, primer
    caracter) reducen los candidatos de edit-distance de ~3671 a ~100 para
    el caso tipico (el typo preserva inicio y longitud). El indice por
    longitud es el fallback cuando el primer caracter cambia.

    Returns:
        (por_longitud, por_longitud_primer_char)
    """
    por_longitud: dict[int, set[str]] = {}
    por_bucket: dict[tuple[int, str], set[str]] = {}
    for tok in vocabulario:
        por_longitud.setdefault(len(tok), set()).add(tok)
        por_bucket.setdefault((len(tok), tok[:1]), set()).add(tok)
    return (
        {lon: frozenset(words) for lon, words in por_longitud.items()},
        {k: frozenset(words) for k, words in por_bucket.items()},
    )


def _distancia_levenshtein(a: str, b: str, max_dist: int) -> int:
    """Levenshtein con banda y early-exit.

    Solo interesa saber si la distancia es <= max_dist. Si la diferencia de
    longitudes ya supera max_dist, corta. Durante la DP, si una fila entera
    queda por encima de max_dist, la distancia final no puede bajar (las
    filas son monotonicas en el peor caso) — se corta temprano.
    """
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        fila_min = i
        for j, cb in enumerate(b, start=1):
            costo = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + costo)
            if curr[j] < fila_min:
                fila_min = curr[j]
        if fila_min > max_dist:
            return max_dist + 1
        prev = curr
    return prev[-1]


def _mejor_candidato(
    lower: str,
    por_longitud: dict[int, frozenset[str]],
    por_bucket: dict[tuple[int, str], frozenset[str]],
    max_dist: int,
) -> str | None:
    """Mejor candidato por Levenshtein con buckets (Capa A, rendimiento).

    Estrategia:
    1. Bucket exacto (longitud, primer char): el typo tipico preserva ambos
       ("prinincipio"->"principio"). ~100 candidatos en vez de ~3671.
    2. Fallback por longitud ±1 con el mismo primer char: insercion/delecion
       que cambia la longitud en 1 ("proseso"->"proceso").
    3. Fallback rango completo de longitud: cubre typos que cambian la
       primera letra ("roseso"->"proceso").

    Cada escaneo pide match unico claro (2do candidato a mayor distancia).
    Retorna None si no hay match <= max_dist en ninguna pasada.
    """
    # 1) Bucket exacto (longitud, primer char) — el caso comun.
    bucket = por_bucket.get((len(lower), lower[:1]))
    if bucket:
        mejor = _scan_candidatos(lower, [(c, len(c)) for c in bucket], max_dist)
        if mejor is not None:
            return mejor

    # 2) Misma primera letra, longitud ±max_dist (insercion/delecion).
    for lon in range(len(lower) - max_dist, len(lower) + max_dist + 1):
        if lon == len(lower):
            continue
        bucket = por_bucket.get((lon, lower[:1]))
        if bucket:
            mejor = _scan_candidatos(lower, [(c, lon) for c in bucket], max_dist)
            if mejor is not None:
                return mejor

    # 3) Fallback rango completo (primer caracter alterado). Ordena por
    #    longitud: exacta primero (lo mas probable), luego ±1, luego ±2.
    #    Pre-filtro de chars comunes para reducir los ~3671 candidatos.
    for paso_lon in (
        (len(lower),),
        (len(lower) - 1, len(lower) + 1),
        (len(lower) - 2, len(lower) + 2),
    ):
        candidatos = [(cand, lon) for lon in paso_lon for cand in por_longitud.get(lon, ())]
        mejor = _scan_candidatos_lento(lower, candidatos, max_dist)
        if mejor is not None:
            return mejor
    return None


def _scan_candidatos(
    lower: str,
    candidatos: list[tuple[str, int]],
    max_dist: int,
) -> str | None:
    """Barre candidatos, retorna el unico con la menor distancia (o None).

    Los candidatos ya vienen reducidos por bucket (longitud, primer char),
    asi que el Levenshtein corre sobre pocos tokens (~100). Sin pre-filtro
    adicional: el early-exit de la distancia corta rapido en no-matches.
    """
    mejor: str | None = None
    mejor_dist = max_dist + 1
    for candidato, _lon in candidatos:
        d = _distancia_levenshtein(lower, candidato, max_dist)
        if d < mejor_dist:
            mejor_dist = d
            mejor = candidato
        elif d == mejor_dist:
            # Empate en distancia: no es un match unico, descartar.
            mejor = None
    if mejor is None or mejor_dist > max_dist:
        return None
    return mejor


def _scan_candidatos_lento(
    lower: str,
    candidatos: list[tuple[str, int]],
    max_dist: int,
) -> str | None:
    """Barre candidatos grandes con pre-filtro de chars comunes.

    Solo se usa en el fallback de rango completo (~3671 candidatos), cuando
    el typo altera la primera letra. El pre-filtro descarta la mayoria antes
    del Levenshtein (3671 -> ~6): si la distancia es <= max_dist, el token y
    el candidato comparten al menos len(token) - max_dist caracteres.
    """
    from collections import Counter

    c_lower = Counter(lower)
    umbral = len(lower) - max_dist
    mejor: str | None = None
    mejor_dist = max_dist + 1
    for candidato, _lon in candidatos:
        if sum((c_lower & Counter(candidato)).values()) < umbral:
            continue
        d = _distancia_levenshtein(lower, candidato, max_dist)
        if d < mejor_dist:
            mejor_dist = d
            mejor = candidato
        elif d == mejor_dist:
            mejor = None
    if mejor is None or mejor_dist > max_dist:
        return None
    return mejor


def _corregir_con_vocabulario(texto: str, vocabulario: frozenset[str]) -> str:
    """Corrige typos por edit-distance contra el vocabulario del corpus.

    Por cada token alfanumerico de 3+ chars que NO este en el vocabulario,
    busca el candidato mas cercano (Levenshtein <= _MAX_EDIT_DIST) filtrando
    por longitud similar (len ± 2, la distancia limita sola). Corrige SOLO si
    hay un match unico claro: el segundo candidato mas cercano esta a mayor
    distancia. Si hay empate o no hay match, conserva el token original
    (defensivo contra apellidos y terminos legitimos desconocidos).

    Case-insensitive: compara en minusculas y devuelve el candidato del
    vocabulario (el embedding es case-insensitive de facto).
    """
    if not vocabulario:
        return _corregir_typos_dict(texto)

    # Indices cacheados: por longitud y por (longitud, primer char) —
    # Capa A rendimiento (reduce candidatos de ~3671 a ~100).
    por_longitud, por_bucket = _indice_por_longitud(vocabulario)

    def _reemplazo(match: re.Match) -> str:
        token = match.group(0)
        if len(token) < _MIN_TOKEN_LEN or not token.isascii():
            return token
        lower = token.lower()
        if lower in vocabulario:
            return token
        candidato = _mejor_candidato(lower, por_longitud, por_bucket, _MAX_EDIT_DIST)
        if candidato is None:
            return token
        return candidato

    # [^\W_]+ (unicode): con [a-zA-Z0-9]+ una tilde partia "presunción" en
    # "presunci" + "n" y el trozo se "corregia" contra el vocabulario ASCII.
    return re.sub(r"[^\W_]+", _reemplazo, texto)


def _corregir_typos_dict(texto: str) -> str:
    """Corrige typos con el dict minimo (fallback sin vocabulario)."""

    def _reemplazo(match: re.Match) -> str:
        token = match.group(0)
        return _TYPOS_JURIDICOS.get(token.lower(), token)

    return _TYPOS_PATTERN.sub(_reemplazo, texto)


def normalizar_query(
    consulta: str,
    vocabulario: frozenset[str] | None = None,
) -> str:
    """Limpia el prefijo ruidoso de la consulta para la búsqueda.

    Args:
        consulta: Texto de la consulta del usuario (con o sin ruido).
        vocabulario: Tokens unicos del corpus (Capa A). Si se provee, los
            typos se corrigen por edit-distance contra el corpus en vez del
            dict minimo. None -> fallback dict (compat/tests).

    Returns:
        Consulta limpia para embedding. Si tras la limpieza queda vacío o
        la limpieza consumió casi todo el texto, retorna el original.
    """
    if not consulta or not consulta.strip():
        return consulta

    limpia = consulta
    for _ in range(_MAX_PASADAS):
        anterior = limpia
        limpia = _PREFIJOS_SALUDO.sub("", limpia)
        limpia = _PREFIJOS_MULETILLA.sub("", limpia)
        limpia = _PREFIJO_INTERROGATIVA.sub("", limpia)
        limpia = _PREFIJO_IMPERATIVO.sub("", limpia)
        limpia = _SUFIJO_IMPERATIVO.sub("", limpia)
        if limpia == anterior:
            break
        limpia = limpia.strip()

    # Correccion de typos: por vocabulario (Capa A) o dict minimo (fallback).
    if vocabulario is not None:
        limpia = _corregir_con_vocabulario(limpia, vocabulario)
    else:
        limpia = _corregir_typos_dict(limpia)

    # Defensivo: no devolver un texto vacío o que haya perdido el núcleo
    # (ej. "hola" a secas). Conservar el original si la limpieza fue total.
    if len(limpia) < 3:
        return consulta
    return limpia


__all__ = ["normalizar_query"]
