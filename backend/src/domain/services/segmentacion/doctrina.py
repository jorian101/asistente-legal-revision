"""Segmentadores para doctrina académica (N3, libros).

Cada libro tiene abreviatura propia (UNIQUE en norma.abreviatura):
'LIB-ATIENZA-INTERP-2019'. Estructura típica del .txt exportado:
- Referencias de imagen por página (líneas lh3 + UUID): delimitan
  páginas (se usan para numerar, luego se descartan; el vault conserva
  el original intacto).
- Portada/créditos/CONTENIDO -> nodo MAESTRO no indexable con la FICHA.
- Cuerpo: ventanas por tamaño (~1800 chars) con el encabezado de
  sección vigente como breadcrumb (no se parte por capítulos: la
  marcación varía por libro).

Cita: autor / obra / página (payload en cada fragmento).
"""

from __future__ import annotations

import re
from collections import Counter

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    enlazar_nodos_jerarquicos,
    partir_bloque_por_tamano,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

RGX_IMAGEN = re.compile(r"^https://lh3\.googleusercontent\.com/\S*$")
RGX_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RGX_SECCION = re.compile(r"^[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 \.,;:\-–\(\)]{9,119}$")
RGX_FIN_FRONT = re.compile(
    r"^(CONTENIDO|ÍNDICE|INDICE|INTRODUCCI[ÓO]N|PRESENTACI[ÓO]N|PR[ÓO]LOGO)",
    re.IGNORECASE,
)


def _paginar(texto: str, lineas_por_pagina: int = 45) -> list[tuple[int, str]]:
    """Divide por marcadores de imagen; devuelve (nro_pagina, texto).

    Si el libro casi no trae marcadores (<10 páginas), fallback por
    líneas: el número es aproximado (metadato `pagina_aprox=True` aguas
    abajo si hace falta distinguirlo).
    """
    paginas: list[tuple[int, str]] = []
    actual: list[str] = []
    nro = 0
    for linea in texto.split("\n"):
        s = linea.strip()
        if RGX_IMAGEN.match(s) or RGX_UUID.match(s):
            if any(ln.strip() for ln in actual):
                nro += 1
                paginas.append((nro, "\n".join(actual)))
                actual = []
            continue
        actual.append(linea)
    if any(ln.strip() for ln in actual):
        nro += 1
        paginas.append((nro, "\n".join(actual)))
    total_lineas = sum(p.count("\n") for _, p in paginas) or 1
    if len(paginas) > 1 and total_lineas / len(paginas) <= 200:
        return paginas
    # Fallback: marcadores escasos frente al volumen (páginas gigantes);
    # trozar de a N líneas (número aproximado).
    lineas = [ln for ln in texto.split("\n") if not RGX_IMAGEN.match(ln.strip())]
    lineas = [ln for ln in lineas if not RGX_UUID.match(ln.strip())]
    return [
        (i // lineas_por_pagina + 1, "\n".join(lineas[i : i + lineas_por_pagina]))
        for i in range(0, len(lineas), lineas_por_pagina)
    ]


def _cabeceras_repetidas(paginas: list[tuple[int, str]]) -> set[str]:
    """Líneas que aparecen en 4+ páginas (headers/footers editoriales)."""
    conteo: Counter[str] = Counter()
    for _, texto in paginas:
        vistas: set[str] = set()
        for linea in texto.split("\n"):
            s = " ".join(linea.split())
            if len(s) >= 12:
                vistas.add(s)
        conteo.update(vistas)
    return {linea for linea, n in conteo.items() if n >= 4}


class SegmentadorLibroBase(SegmentadorNorma):
    """Base para libros: la subclase fija ABREVIATURA/NOMBRE/FICHA."""

    ABREVIATURA = ""
    NOMBRE = ""
    #: Ficha citable: autor, obra, anio, materia.
    FICHA: dict[str, str] = {}

    REGEX_ARTICULO = RGX_SECCION
    REGEX_ESTRUCTURA = {}
    LIMPIEZA_PROPIA = True

    # NOTE: la base nunca se instancia (ABREVIATURA vacía -> TypeError
    # en __init__); cada libro es una subclase.


def _limpio(paginas_texto: str, ruido: set[str]) -> str:
    """Quita líneas vacías y cabeceras editoriales repetidas."""
    return "\n".join(
        ln for ln in paginas_texto.split("\n") if ln.strip() and ln.strip() not in ruido
    ).strip()


def _segmentar_libro(seg: SegmentadorLibroBase, texto_completo: str) -> ArbolJerarquico:
    from src.domain.services.segmentacion.base import limpiar_texto_ocr

    abrev = seg.ABREVIATURA
    ficha = seg.FICHA
    # Paginar ANTES de limpiar: limpiar_texto_ocr une líneas y destruye
    # los marcadores de página (image-refs). Se limpia página por página.
    paginas = _paginar(seg._strip_basic(texto_completo))
    if not paginas:
        raise ValueError(f"Texto vacío o sin páginas: {abrev}")
    paginas = [(nro, limpiar_texto_ocr(pag)) for nro, pag in paginas]
    ruido = _cabeceras_repetidas(paginas)

    nodos: dict[str, NodoJerarquico] = {}
    ocurrencias: list[tuple[int, str, int]] = []
    raices: list[str] = []
    fragmentos: list[FragmentoProducible] = []

    # Maestro no indexable: portada + ficha. El frente termina en la
    # primera página con CONTENIDO/INTRODUCCIÓN (o página 3 como tope).
    idx_cuerpo = min(3, len(paginas))
    for i, (_nro, pag) in enumerate(paginas[:4]):
        if RGX_FIN_FRONT.search(_limpio(pag, ruido)[:400]):
            idx_cuerpo = i + 1
            break
    resto = paginas[idx_cuerpo:]

    clave_maestro = f"{abrev}_MASTER"
    nodos[clave_maestro] = NodoJerarquico(
        clave=clave_maestro,
        nivel=1,
        titulo=ficha.get("obra", abrev),
        hijos=[],
        metadatos={
            "tipo_estructura": "MAESTRO_LIBRO",
            "no_indexable": True,
            **ficha,
        },
    )
    raices.append(clave_maestro)

    # Cuerpo: ventanas con sección vigente como breadcrumb + página.
    seccion = "GENERAL"
    pos = 0
    for nro, _pagina in resto:
        for linea in _pagina.split("\n"):
            s = linea.strip()
            if not s or s in ruido:
                continue
            if RGX_SECCION.match(s) and len(s) <= 120:
                seccion = s
        cuerpo = _limpio(_pagina, ruido)
        if not cuerpo:
            continue
        clave_nodo = f"{abrev}_SEC"
        if clave_nodo not in nodos:
            nodos[clave_nodo] = NodoJerarquico(
                clave=clave_nodo,
                nivel=2,
                titulo="CUERPO",
                hijos=[],
                metadatos={"tipo_estructura": "BLOQUE_DOCTRINA"},
            )
            ocurrencias.append((pos, clave_nodo, 2))
        slug = re.sub(r"[^A-Z0-9]+", "_", seccion[:24].upper()).strip("_")
        for j, parte in enumerate(partir_bloque_por_tamano(cuerpo)):
            suf = "" if j == 0 else f"-p{j + 1}"
            fragmentos.append(
                FragmentoProducible(
                    texto=parte,
                    nivel_jerarquico=4,
                    tipo_chunk="doctrina_seccion",
                    padre_ref_key=f"{clave_nodo}-{slug or 'GENERAL'}-{nro}{suf}",
                    metadatos={
                        "bloque": "doctrina",
                        "autor": ficha.get("autor", ""),
                        "obra": ficha.get("obra", abrev),
                        "pagina": nro,
                        "seccion": seccion,
                    },
                )
            )
        pos += 1

    if not fragmentos:
        raise ValueError(f"Sin cuerpo indexable tras limpieza: {abrev}")
    enlazar_nodos_jerarquicos(nodos, ocurrencias)
    return ArbolJerarquico(abreviatura=abrev, raices=raices, nodos=nodos, fragmentos=fragmentos)


def _libro(
    abreviatura: str,
    nombre: str,
    ficha: dict[str, str],
) -> type[SegmentadorLibroBase]:
    """Fábrica de subclases por libro (una línea por ficha)."""

    def _segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_libro(self, texto_completo)

    seg_cls = type(
        f"Segmentador{abreviatura.replace('-', '_')}",
        (SegmentadorLibroBase,),
        {
            "ABREVIATURA": abreviatura,
            "NOMBRE": nombre,
            "FICHA": ficha,
            "segmentar": _segmentar,
        },
    )
    return seg_cls


_LIBROS = [
    (
        "LIB-ARG-OPTICA-FORENSE",
        "Argumentación jurídica. Fisonomía desde una óptica forense (UNAM, 2014)",
        {
            "autor": "Mayolo García García / Rodolfo Moreno Cruz (coords.)",
            "obra": "Argumentación jurídica. Fisonomía desde una óptica forense",
            "anio": "2014",
            "materia": "argumentacion",
        },
    ),
    (
        "LIB-ARG-PRINCIPALISTA",
        "Estudios sobre la argumentación jurídica principalista (UNAM)",
        {
            "autor": "Instituto de Investigaciones Jurídicas UNAM",
            "obra": "Estudios sobre la argumentación jurídica principalista",
            "anio": "",
            "materia": "argumentacion",
        },
    ),
    (
        "LIB-ARG-EVALUACION",
        "Argumentación jurídica y sus criterios de evaluación (UNAM)",
        {
            "autor": "Instituto de Investigaciones Jurídicas UNAM",
            "obra": "Argumentación jurídica y sus criterios de evaluación",
            "anio": "",
            "materia": "argumentacion",
        },
    ),
    (
        "LIB-ARG-LENGUAJE",
        "Argumentación y lenguaje jurídico (UNAM)",
        {
            "autor": "Instituto de Investigaciones Jurídicas UNAM",
            "obra": "Argumentación y lenguaje jurídico",
            "anio": "",
            "materia": "argumentacion",
        },
    ),
    (
        "LIB-RAZONES-DERECHO",
        "Las razones del derecho (UNAM, Doctrina Jurídica 134)",
        {
            "autor": "Por verificar en portada",
            "obra": "Las razones del derecho. Teorías de la argumentación jurídica",
            "anio": "",
            "materia": "argumentacion",
        },
    ),
    (
        "LIB-ATIENZA-INTERP-2019",
        "Interpretación constitucional (Atienza, TCP Bolivia, 2019)",
        {
            "autor": "Manuel Atienza Rodríguez",
            "obra": "Interpretación constitucional",
            "anio": "2019",
            "materia": "interpretacion_constitucional",
        },
    ),
    (
        "LIB-INTERP-CONST-BOLIVIA",
        "La interpretación constitucional en Bolivia",
        {
            "autor": "Por verificar en portada",
            "obra": "La interpretación constitucional en Bolivia",
            "anio": "",
            "materia": "interpretacion_constitucional",
        },
    ),
    (
        "LIB-DEBATE-PONDERACION",
        "Un debate sobre la ponderación (García Amado / Atienza, TCP Bolivia)",
        {
            "autor": "Juan Antonio García Amado / Manuel Atienza Rodríguez",
            "obra": "Un debate sobre la ponderación",
            "anio": "",
            "materia": "ponderacion",
        },
    ),
    (
        "LIB-GUIA-CASO-DELITO",
        "Guía sobre teoría del caso y teoría del delito",
        {
            "autor": "Por verificar en portada",
            "obra": "Guía sobre teoría del caso y teoría del delito",
            "anio": "",
            "materia": "teoria_caso",
        },
    ),
    (
        "LIB-MANUAL-DESCOMP-2024",
        "Manual de descomposición del tipo penal (Hinojosa / Condori, 2024)",
        {
            "autor": "Winter R. Hinojosa Téllez / Marco A. Condori Mamani",
            "obra": "Manual de descomposición del tipo penal",
            "anio": "2024",
            "materia": "tipo_penal",
        },
    ),
    (
        "LIB-ANALISIS-FE-PUBLICA",
        "Análisis del tipo penal. Delitos contra la fe pública",
        {
            "autor": "Por verificar en portada",
            "obra": "Análisis del tipo penal. Delitos contra la fe pública",
            "anio": "",
            "materia": "tipo_penal",
        },
    ),
]

for _abrev, _nombre, _ficha in _LIBROS:
    SegmentadorRegistry.registrar(_abrev, _libro(_abrev, _nombre, _ficha))
