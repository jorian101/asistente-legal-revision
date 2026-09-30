"""Segmentación de normas jurídicas — Interfaces y Value Objects.

Este módulo define el contrato que debe cumplir cada segmentador específico
por corpus (CPPM, CPM, LOJM, LOFA, CPE, LEY1970_CP, LEY1970_CPP).

Clean Architecture: los segmentadores viven en el dominio (sin dependencias
de infraestructura). Los adaptadores de extracción (PyMuPDF) están en
application/ports y se inyectan vía puertos.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

# ----- Value Objects --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FragmentoProducible:
    """Un fragmento listo para persistir (sin ID ni qdrant_point_id).

    Atributos:
        texto: Contenido textual del fragmento (ya limpio, sin OCR artifacts).
        nivel_jerarquico: 1..4 (ver NivelJerarquico en entities.fragmento).
        tipo_chunk: Tipo semántico (ver TipoChunk en entities.fragmento).
        padre_ref_key: Clave semántica del padre (ej: 'CPPM_184_MASTER').
            None para fragmentos de nivel 1 (raíces estructurales).
        metadatos: Dict libre; campos típicos: 'numero_articulo', 'titulo',
            'subnumerales', 'incisos', 'tema', 'funcion'.
        es_indexable: True si debe ir a Qdrant con vector; False si solo
            sirve como contexto jerárquico (estructura).
    """

    texto: str
    nivel_jerarquico: Literal[1, 2, 3, 4]
    tipo_chunk: str
    padre_ref_key: str | None
    metadatos: dict[str, Any]
    es_indexable: bool = True


@dataclass(frozen=True, slots=True)
class NodoJerarquico:
    """Nodo del árbol jerárquico de una norma.

    Representa un elemento estructural (parte, libro, título, capítulo)
    que agrupa artículos pero NO es un fragmento indexable por sí mismo.

    Atributos:
        clave: Identificador semántico único (ej: 'CPPM_LIBRO_I',
            'CPPM_TITULO_II', 'CPPM_CAPITULO_1').
        nivel: 1 (parte/libro) | 2 (título) | 3 (capítulo).
        titulo: Texto visible del nodo (ej: 'LIBRO PRIMERO', 'TÍTULO I').
        hijos: Lista de claves de nodos hijos o fragmentos.
        metadatos: Información adicional (rango de artículos, etc.).
    """

    clave: str
    nivel: Literal[1, 2, 3]
    titulo: str
    hijos: list[str]
    metadatos: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ArbolJerarquico:
    """Árbol jerárquico completo de una norma segmentada.

    Atributos:
        abreviatura: Abreviatura de la norma (ej: 'CPPM').
        raices: Lista de claves de nodos de nivel 1.
        nodos: Dict clave -> NodoJerarquico (todos los niveles 1..3).
        fragmentos: Lista de FragmentoProducible (nivel 4, los indexables).
    """

    abreviatura: str
    raices: list[str]
    nodos: dict[str, NodoJerarquico]
    fragmentos: list[FragmentoProducible]


# ----- Protocolo del Segmentador -------------------------------------------


class SegmentadorNorma(ABC):
    """Contrato que implementa cada segmentador por corpus.

    Cada corpus (CPPM, CPM, CPE, LOJM, LOFA, CP, CPP)
    tiene su propia implementación porque la estructura interna, numeración
    y formularios varían significativamente.

    El segmento NO hace I/O ni llama a extractores; recibe el texto
    completo ya extraído (RAW o MARKDOWN) y devuelve el árbol + fragmentos.
    """

    #: Abreviatura canónica de la norma (ej: 'CPPM'). Debe coincidir con
    #: Norma.abreviatura y usarse en claves semánticas (CPPM_1, CPPM_LIBRO_I).
    ABREVIATURA: str

    #: Nombre legal completo de la norma (ej: 'Código Penal (...)' ). Si viene
    #: vacío, IndexarNorma lo deriva del nombre de clase (legacy). Usarlo evita
    #: que Norma.nombre quede con un token interno tipo 'LEY1970CP'.
    NOMBRE: str = ""

    #: Regex para detectar inicio de artículo en el texto RAW extraído.
    #: Captura el número de artículo en grupo 1.
    REGEX_ARTICULO: re.Pattern[str]

    #: Regex opcionales para detectar estructuras superiores.
    #: Clave -> (regex, nivel). Se usan para poblar el árbol jerárquico.
    REGEX_ESTRUCTURA: dict[str, tuple[re.Pattern[str], Literal[1, 2, 3]]]

    #: Si True, IndexarNorma NO aplica limpiar_texto_ocr global: el
    #: segmentador limpia a su manera (p.ej. libros: pagina primero para
    #: no destruir los marcadores de página).
    LIMPIEZA_PROPIA: bool = False

    def __init__(self) -> None:
        if not hasattr(self, "ABREVIATURA") or not self.ABREVIATURA:
            raise TypeError(f"{self.__class__.__name__} debe definir ABREVIATURA")
        if not hasattr(self, "REGEX_ARTICULO") or not self.REGEX_ARTICULO:
            raise TypeError(f"{self.__class__.__name__} debe definir REGEX_ARTICULO")
        if not hasattr(self, "REGEX_ESTRUCTURA"):
            self.REGEX_ESTRUCTURA = {}

    @abstractmethod
    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        """Segmenta el texto completo de la norma.

        Args:
            texto_completo: Texto ya extraído del PDF (modo RAW recomendado).

        Returns:
            ArbolJerarquico con nodos estructurales (niveles 1-3) y
            fragmentos indexables (nivel 4).
        """
        ...

    # ----- Helpers comunes --------------------------------------------------

    def _strip_basic(self, texto: str) -> str:
        """Limpieza mínima post-extracción: \r, soft hyphen, zero-width space.

        NO aplica NFKC ni une líneas. Para normalización completa previa a la
        segmentación, usar `limpiar_texto_ocr()` del módulo (a nivel de pipeline).
        Mantener separado evita aplicar NFKC dos veces y romper regex que dependen
        de caracteres colapsados por la normalización (ej: º -> o).
        """
        return (
            texto.replace("\r", "")
            .replace("\u00ad", "")  # soft hyphen
            .replace("\u200b", "")  # zero width space
            .strip()
        )

    def _es_articulo_derogado(self, texto_articulo: str) -> bool:
        """Detecta si el texto indica artículo derogado."""
        texto_lower = texto_articulo.lower()
        return any(
            k in texto_lower
            for k in (
                "derogado",
                "derogada",
                "abrogado",
                "abrogada",
                "sin efecto",
                "vigencia agotada",
            )
        )

    def _extraer_numero_articulo(self, match: re.Match[str]) -> int:
        """Extrae el número de artículo del match (grupo 1 por convención)."""
        grupo = match.group(1)
        if grupo:
            return int(grupo)
        # Fallback: buscar primer número en el match completo
        m = re.search(r"\d+", match.group(0))
        return int(m.group()) if m else 0


# ----- Estructura jerárquica (D-S2C-06 split) -------------------------------


def enlazar_nodos_jerarquicos(
    nodos: dict[str, NodoJerarquico],
    ocurrencias: list[tuple[int, str, int]],
) -> None:
    """Enlaza padres e hijos del árbol por posición en el texto.

    D-S2C-06 (split, sin wiring): solo completa `hijos`; no cambia raices,
    claves ni fragmentos. El wiring de `padre_ref_id` va en el ciclo s5.
    Cada ocurrencia es (posicion, clave, nivel); se ordenan por posición y
    se usa una pila por nivel: el padre es el nodo abierto de nivel menor.
    """
    pila: list[tuple[int, str]] = []
    for _, clave, nivel in sorted(ocurrencias):
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        if pila:
            padre = nodos.get(pila[-1][1])
            if padre is not None and clave not in padre.hijos:
                padre.hijos.append(clave)
        pila.append((nivel, clave))


def clave_unica(nodos: dict[str, NodoJerarquico], base: str) -> str:
    """El mismo encabezado se repite en cada Parte (LIBRO PRIMERO, TÍTULO I...):
    la primera aparición conserva `base`; las siguientes llevan sufijo `_2`, `_3`..."""
    if base not in nodos:
        return base
    n = 2
    while f"{base}_{n}" in nodos:
        n += 1
    return f"{base}_{n}"


def tipo_chunk_estructural(clave_tipo: str) -> str:
    """Mapea el tipo de estructura al TipoChunk estructural del dominio."""
    return {
        "PARTE": "estructura_parte",
        "LIBRO": "estructura_libro",
        "TITULO": "estructura_titulo",
        "CAPITULO": "estructura_capitulo",
        "SECCION": "estructura_seccion",
    }.get(clave_tipo, "estructura_padre")


# ----- Limpieza de texto (shared) -----------------------------------------


_INICIO_ENCABEZADO = re.compile(
    r"(?:Art[ií]culo|ART[IÍ]CULO)\s+\d"
    r"|(?:LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+\S"
    r"|(?:PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\s+PARTE"
)


def limpiar_texto_ocr(texto: str) -> str:
    """Heurísticas para limpiar artefactos de OCR antes de segmentar.

    Args:
        texto: Texto crudo extraído del PDF (RAW mode).

    Returns:
        Texto normalizado: Unicode NFKC, quita soft hyphens, corrige
        espacios múltiples, une líneas rotas mid-sentence, etc.
    """
    import unicodedata

    t = unicodedata.normalize("NFKC", texto)
    # Soft hyphens y zero-width
    t = t.replace("\u00ad", "").replace("\u200b", "")
    # Normalizar saltos de línea Windows/Unix
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    # Unir líneas que fueron rotas en medio de oración (no terminan en . : ; ? !)
    lineas = t.split("\n")
    unidas: list[str] = []
    buffer = ""
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            if buffer:
                unidas.append(buffer)
                buffer = ""
            continue
        if buffer:
            # Si buffer no termina en puntuación fuerte, es continuación, salvo que la
            # línea abra un encabezado (Artículo/LIBRO/TÍTULO/...): nunca se pega a la
            # anterior (p. ej. tras una nota "(Modificado por ...)" sin punto final).
            if buffer.rstrip()[-1] not in ".?!:;" and not _INICIO_ENCABEZADO.match(linea):
                buffer += " " + linea
            else:
                unidas.append(buffer)
                buffer = linea
        else:
            buffer = linea
    if buffer:
        unidas.append(buffer)
    t = "\n".join(unidas)
    # Espacios múltiples -> uno
    t = re.sub(r"[ \t]+", " ", t)
    return t


# ----- Utilidad para partir bloques largos por párrafos ----------------------


def partir_bloque_por_tamano(
    texto: str,
    max_chars: int = 1800,
) -> list[str]:
    """Parte un bloque largo por párrafos dobles con tope de tamaño.

    Para jurisprudencia (bloques hecho/derecho de 400-700 tokens): si un
    párrafo supera el tope, se corta por oraciones. Nunca devuelve vacíos.
    """
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    partes: list[str] = []
    for p in parrafos:
        while len(p) > max_chars:
            corte = max(p.rfind(". ", 0, max_chars), p.rfind("\n", 0, max_chars))
            corte = corte + 1 if corte > 0 else max_chars
            partes.append(p[:corte].strip())
            p = p[corte:].strip()
        if p:
            partes.append(p)
    return partes


# ----- Utilidad para fragmentar un artículo en párrafos/numerales ---------

# Patrones de numerales: (1) 1. (i) (ii) a) b) I. II. etc.
# Compilado a nivel de módulo: re.compile se ejecuta una vez, no en cada llamada
# a particionar_articulo (que se invierte miles de veces por ingesta de corpus).
_NUMERAL_REGEX = re.compile(
    r"(?:^|\n)\s*(?:\((\d+)\)|(\d+)\.|\(([ivx]+)\)|([a-z])\)|([IVX]+)\.)\s*",
    re.IGNORECASE | re.MULTILINE,
)


def particionar_articulo(
    texto: str,
    abreviatura: str,
    numero_articulo: int,
    tipo_base: str,
    padre_ref_key: str,
) -> list[FragmentoProducible]:
    """Particiona un artículo en sub-fragmentos indexables.

    Estrategia por defecto (se puede sobreescribir en segmentadores):
    0. Si hay texto antes del primer numeral (introducción con tipo penal
       y/o sanción común), se emite primero como fragmento maestro con la
       clave padre_ref_key — los numerales la heredan (Tabla 18).
    1. Dividir por numerales (1), (2), (i), (ii), 1., 2., etc.
    2. Si no hay numerales, dividir por párrafos dobles \n\n
    3. Si un párrafo > 800 chars, subdividir por oraciones.

    Args:
        texto: Texto del artículo (sin cabecera 'ARTÍCULO N°—').
        abreviatura: Ej: 'CPPM'.
        numero_articulo: Número del artículo.
        tipo_base: Tipo base del chunk (ej: 'articulo_multiparagrafo').
        padre_ref_key: Clave semántica del padre (ej: 'CPPM_184_MASTER').

    Returns:
        Lista de FragmentoProducible (nivel 4).
    """
    matches = list(_NUMERAL_REGEX.finditer(texto))
    partes: list[FragmentoProducible] = []
    if len(matches) >= 2:
        # D-S2C-01: la introducción (tipo penal, sanción común) no se
        # descarta: se emite como fragmento maestro con la clave padre,
        # que los numerales heredan vía padre_ref_key.
        intro = texto[: matches[0].start()].strip()
        if intro:
            partes.append(
                FragmentoProducible(
                    texto=intro,
                    nivel_jerarquico=4,
                    tipo_chunk=tipo_base,
                    padre_ref_key=padre_ref_key,
                    metadatos={
                        "numero_articulo": numero_articulo,
                        "tipo_original": tipo_base,
                    },
                )
            )
        # Hay numerales → partir por ellos
        partes_numeral: list[tuple[str, str]] = []  # (num_numeral, texto)
        for i, m in enumerate(matches):
            fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
            num = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
            partes_numeral.append((num or str(i + 1), texto[m.start() : fin].strip()))

        partes.extend(
            FragmentoProducible(
                texto=p[1],
                nivel_jerarquico=4,
                tipo_chunk=f"{tipo_base}_numeral",
                padre_ref_key=f"{padre_ref_key}_{p[0]}",
                metadatos={
                    "numero_articulo": numero_articulo,
                    "numeral": p[0],
                    "tipo_original": tipo_base,
                },
                es_indexable=True,
            )
            for p in partes_numeral
            if p[1]
        )
        return partes

    # Sin numerales → partir por párrafos dobles
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if len(parrafos) == 1:
        return [
            FragmentoProducible(
                texto=parrafos[0],
                nivel_jerarquico=4,
                tipo_chunk=f"{tipo_base}",
                padre_ref_key=padre_ref_key,
                metadatos={
                    "numero_articulo": numero_articulo,
                    "tipo_original": tipo_base,
                },
                es_indexable=True,
            )
        ]

    # Múltiples párrafos
    return [
        FragmentoProducible(
            texto=p,
            nivel_jerarquico=4,
            tipo_chunk=f"{tipo_base}_parrafo",
            padre_ref_key=f"{padre_ref_key}_p{i + 1}",
            metadatos={
                "numero_articulo": numero_articulo,
                "parrafo": i + 1,
                "tipo_original": tipo_base,
            },
            es_indexable=True,
        )
        for i, p in enumerate(parrafos)
    ]
