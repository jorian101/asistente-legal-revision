"""Segmentadores para Sentencias Constitucionales Plurinacionales (SCP).

Estructura rígida de toda SCP (tesis Tabla 19):
- Encabezado jurisdiccional (SENTENCIA.../Sala/Magistrado/Acción/Expediente)
  -> nodo MAESTRO no indexable (metadatos, nunca va a Qdrant).
- I. ANTECEDENTES CON RELEVANCIA JURÍDICA -> bloque HECHO (indexable).
- II. CONCLUSIONES -> bloque HECHO (indexable).
- III. FUNDAMENTOS JURÍDICOS DEL FALLO -> bloque DERECHO (indexable).
- Resolutiva ("en revisión, resuelve: ...") -> bloque FALLO (indexable).

Lo que se vuelve "norma" es la ratio (derecho + fallo), no el caso ajeno:
los antecedentes se recortan al hecho-tipo y el maestro no se indexa.

Cada sentencia tiene abreviatura propia (UNIQUE en norma.abreviatura):
'SCP-0623-2024-S4'. Las claves semánticas usan esa abreviatura para no
colisionar entre sentencias (padre_ref_key).
"""

from __future__ import annotations

import re

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    enlazar_nodos_jerarquicos,
    partir_bloque_por_tamano,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

RGX_CABECERA = re.compile(r"SENTENCIA CONSTITUCIONAL PLURINACIONAL\s+(\S+)", re.IGNORECASE)
RGX_SALA = re.compile(r"^(SALA .+)$", re.IGNORECASE | re.MULTILINE)
RGX_MAGISTRADO = re.compile(r"Magistrad[oa] Relator[a]?:\s*(.+)", re.IGNORECASE)
RGX_ACCION = re.compile(r"^((?:Acción|Recurso)[^\n]*)", re.IGNORECASE | re.MULTILINE)
RGX_EXPEDIENTE = re.compile(r"Expediente:\s*(\S+)", re.IGNORECASE)
RGX_FECHA_SEDE = re.compile(r"Sucre,\s*(\d{1,2} de \w+ de \d{4})", re.IGNORECASE)

# Sin ancla ^ : el texto llega con sangrías y `limpiar_texto_ocr` une
# líneas (el encabezado "I. ANTECEDENTES..." no termina en puntuación
# fuerte y se fusiona con la línea siguiente). (?<!\S) = inicio o espacio.
RGX_SEC_ANTECEDENTES = re.compile(
    r"(?<!\S)I\.\s+ANTECEDENTES CON RELEVANCIA JUR[ÍI]DICA", re.IGNORECASE
)
RGX_SEC_CONCLUSIONES = re.compile(r"(?<!\S)II\.\s+CONCLUSIONES", re.IGNORECASE)
RGX_SEC_FUNDAMENTOS = re.compile(
    r"(?<!\S)III\.\s+FUNDAMENTOS JUR[ÍI]DICOS DEL FALLO", re.IGNORECASE
)
# Resolutiva: SCP nuevas "en revisión, resuelve:"; SC viejas "POR TANTO".
RGX_RESUELVE = re.compile(r"(?:en revisi[óo]n,\s*resuelve\s*:|POR TANTO)", re.IGNORECASE)
RGX_SUBSEC = re.compile(r"(?<!\S)((?:I|II|III)\.\d+(?:\.\d+)?)\.\s*(\S.{0,80})")
# Para el detector de patrones: los marcadores de subsección.
RGX_MUESTRA = re.compile(r"^(?:I|II|III)\.\d+", re.MULTILINE)


class SegmentadorSCPBase(SegmentadorNorma):
    """Base para SCP: la subclase fija ABREVIATURA/NOMBRE/METADATOS_FICHA."""

    ABREVIATURA = ""  # la fija cada sentencia (ej: 'SCP-0623-2024-S4')
    NOMBRE = ""
    #: Metadatos jurisdiccionales de la ficha (accion, expediente, fecha...).
    METADATOS_FICHA: dict[str, str] = {}

    # Detector: cuenta subsecciones I.1/II.1/III.1 en la muestra.
    REGEX_ARTICULO = RGX_MUESTRA
    REGEX_ESTRUCTURA = {
        "ANTECEDENTES": (RGX_SEC_ANTECEDENTES, 1),
        "CONCLUSIONES": (RGX_SEC_CONCLUSIONES, 1),
        "FUNDAMENTOS": (RGX_SEC_FUNDAMENTOS, 1),
    }

    # NOTE: la base nunca se instancia (ABREVIATURA vacía -> TypeError
    # en __init__); cada sentencia es una subclase que implementa segmentar.


def _segmentar_scp(seg: SegmentadorSCPBase, texto_completo: str) -> ArbolJerarquico:
    abrev = seg.ABREVIATURA
    texto = seg._strip_basic(texto_completo)

    m_ant = RGX_SEC_ANTECEDENTES.search(texto)
    m_con = RGX_SEC_CONCLUSIONES.search(texto)
    m_fun = RGX_SEC_FUNDAMENTOS.search(texto)
    m_res = RGX_RESUELVE.search(texto)
    if not (m_ant and m_con and m_fun):
        raise ValueError(f"Texto no parece SCP (faltan secciones I/II/III): {abrev}")

    nodos: dict[str, NodoJerarquico] = {}
    ocurrencias: list[tuple[int, str, int]] = []
    raices: list[str] = []
    fragmentos: list[FragmentoProducible] = []

    # Maestro no indexable: metadatos jurisdiccionales (tesis Tabla 19).
    clave_maestro = f"{abrev}_MASTER"
    cab = RGX_CABECERA.search(texto)
    nodos[clave_maestro] = NodoJerarquico(
        clave=clave_maestro,
        nivel=1,
        titulo=(cab.group(0).strip() if cab else f"SENTENCIA {abrev}"),
        hijos=[],
        metadatos={
            "tipo_estructura": "MAESTRO_SCP",
            "no_indexable": True,
            **seg.METADATOS_FICHA,
        },
    )
    raices.append(clave_maestro)

    bloques = [
        ("HECHO", m_ant.start(), m_con.start(), "fundamento_de_hecho"),
        ("HECHO", m_con.start(), m_fun.start(), "fundamento_de_hecho"),
        (
            "DERECHO",
            m_fun.start(),
            m_res.start() if m_res else len(texto),
            "fundamento_de_derecho_analisis",
        ),
    ]
    if m_res:
        bloques.append(("FALLO", m_res.start(), len(texto), "fundamentacion_del_fallo"))

    for nombre_bloque, inicio, fin, tipo_chunk in bloques:
        clave_nodo = f"{abrev}_{nombre_bloque}"
        cuerpo = texto[inicio:fin].strip()
        nodos[clave_nodo] = NodoJerarquico(
            clave=clave_nodo,
            nivel=2,
            titulo=nombre_bloque,
            hijos=[],
            metadatos={"tipo_estructura": f"BLOQUE_{nombre_bloque}"},
        )
        ocurrencias.append((inicio, clave_nodo, 2))

        # Subsecciones (I.1, II.2, III.3...) o bloque entero por tamaño.
        subs = list(RGX_SUBSEC.finditer(cuerpo))
        if subs:
            for i, sm in enumerate(subs):
                fin_sub = subs[i + 1].start() if i + 1 < len(subs) else len(cuerpo)
                texto_sub = cuerpo[sm.start() : fin_sub].strip()
                sufijo = sm.group(1).replace(".", "-")
                for j, parte in enumerate(partir_bloque_por_tamano(texto_sub)):
                    suf = f"{sufijo}" if j == 0 else f"{sufijo}-p{j + 1}"
                    fragmentos.append(
                        FragmentoProducible(
                            texto=parte,
                            nivel_jerarquico=4,
                            tipo_chunk=tipo_chunk,
                            padre_ref_key=f"{clave_nodo}_{suf}",
                            metadatos={
                                "bloque": nombre_bloque.lower(),
                                "subseccion": sm.group(1),
                                "numero_sentencia": abrev,
                            },
                        )
                    )
        else:
            for j, parte in enumerate(partir_bloque_por_tamano(cuerpo)):
                suf = "" if j == 0 else f"-p{j + 1}"
                fragmentos.append(
                    FragmentoProducible(
                        texto=parte,
                        nivel_jerarquico=4,
                        tipo_chunk=tipo_chunk,
                        padre_ref_key=f"{clave_nodo}{suf}",
                        metadatos={
                            "bloque": nombre_bloque.lower(),
                            "numero_sentencia": abrev,
                        },
                    )
                )

    enlazar_nodos_jerarquicos(nodos, ocurrencias)
    return ArbolJerarquico(abreviatura=abrev, raices=raices, nodos=nodos, fragmentos=fragmentos)


class SegmentadorSCP0623(SegmentadorSCPBase):
    """SCP 0623/2024-S4 — saneamiento del iter procesal, nulidad de oficio."""

    ABREVIATURA = "SCP-0623-2024-S4"
    NOMBRE = (
        "Sentencia Constitucional Plurinacional 0623/2024-S4 "
        "(saneamiento del iter procesal, nulidad de oficio)"
    )
    METADATOS_FICHA = {
        "numero": "0623/2024-S4",
        "organo": "TCP Sala Cuarta Especializada",
        "accion": "Acción de libertad",
        "fecha": "2024-09-17",
        "materia": "saneamiento_procesal",
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_scp(self, texto_completo)


class SegmentadorSCP0663(SegmentadorSCPBase):
    """SCP 0663/2025-S2 — motivación, fundamentación y congruencia."""

    ABREVIATURA = "SCP-0663-2025-S2"
    NOMBRE = (
        "Sentencia Constitucional Plurinacional 0663/2025-S2 "
        "(motivación, fundamentación y congruencia)"
    )
    METADATOS_FICHA = {
        "numero": "0663/2025-S2",
        "organo": "TCP Sala Segunda Especializada",
        "accion": "Acción de amparo constitucional",
        "fecha": "2025",
        "materia": "motivacion",
    }

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_scp(self, texto_completo)


def _segmentar_scp_ficha(
    abreviatura: str, nombre: str, ficha: dict[str, str]
) -> SegmentadorSCPBase:
    """Fábrica de segmentadores SCP por ficha (una línea por sentencia)."""

    def _segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_scp(self, texto_completo)

    seg_cls = type(
        f"Segmentador{abreviatura.replace('-', '_')}",
        (SegmentadorSCPBase,),
        {
            "ABREVIATURA": abreviatura,
            "NOMBRE": nombre,
            "METADATOS_FICHA": ficha,
            "segmentar": _segmentar,
        },
    )
    return seg_cls


_FICHAS_SCP = [
    (
        "SC-1180-2011-R",
        "Sentencia Constitucional 1180/2011-R (Ley 1970 supletoria)",
        {
            "numero": "1180/2011-R",
            "organo": "TCP",
            "accion": "Acción de libertad",
            "fecha": "2011-09-06",
            "materia": "supletoriedad_ley1970",
        },
    ),
    (
        "SCP-0013-2016",
        "Sentencia Constitucional Plurinacional 0013/2016 (competencia restringida)",
        {
            "numero": "0013/2016",
            "organo": "TCP Sala Plena",
            "accion": "Acción de amparo constitucional",
            "fecha": "2016-02-01",
            "materia": "competencia_restringida",
        },
    ),
    (
        "SC-0110-2004",
        "Sentencia Constitucional 0110/2004 (plazo razonable, mora procesal)",
        {
            "numero": "0110/2004",
            "organo": "TCP",
            "accion": "Recurso indirecto de inconstitucionalidad",
            "fecha": "2004-10-05",
            "materia": "plazo_razonable",
        },
    ),
    (
        "SC-2540-2012",
        "Sentencia Constitucional Plurinacional 2540/2012 (conflicto de competencias)",
        {
            "numero": "2540/2012",
            "organo": "TCP Sala Plena",
            "accion": "Conflicto de competencias jurisdiccionales",
            "fecha": "2012-12-21",
            "materia": "competencia_restringida",
        },
    ),
]

SegmentadorRegistry.registrar("SCP-0623-2024-S4", SegmentadorSCP0623)
SegmentadorRegistry.registrar("SCP-0663-2025-S2", SegmentadorSCP0663)
for _abrev, _nombre, _ficha in _FICHAS_SCP:
    SegmentadorRegistry.registrar(_abrev, _segmentar_scp_ficha(_abrev, _nombre, _ficha))
