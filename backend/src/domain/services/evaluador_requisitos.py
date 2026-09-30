"""Servicio de dominio: requisitos mínimos de obrados por tipo de caso.

Fuente vault (sin sprints/):
- wiki/document-types/taxonomia-documentos.md §A (Documentos de entrada)
- wiki/teoria/proceso-sac-detallado.md + wiki/workflows/flujo-procesal-consulta.md

Solo piezas que LLEGAN con el expediente (las que sube el supervisor).
Las generadas en TSJM (Relación de Obrados, Dictamen de Fondo, Auto de
Vista) no se exigen al aperturar.
"""

from __future__ import annotations

REQUISITOS: dict[str, set[str]] = {
    # Grado de Consulta: Sentencia + Acta de Lectura + Oficio (Art 194 CPPM)
    "consulta": {"sentencia", "acta_audiencia", "oficio_elevacion"},
    # Apelación incidental / restringida: resolución recurrida + memorial + oficio
    "apelacion_incidental": {
        "auto_interlocutorio",
        "memorial_apelacion",
        "oficio_elevacion",
    },
    "apelacion_restringida": {
        "sentencia",
        "memorial_apelacion",
        "oficio_elevacion",
    },
}

NOMBRES: dict[str, str] = {
    "sentencia": "Sentencia (N° y fecha)",
    "acta_audiencia": "Acta de Audiencia Pública de Lectura",
    "oficio_elevacion": "Oficio de Elevación del TPJM",
    "auto_interlocutorio": "Auto Interlocutorio / Resolución recurrida",
    "memorial_apelacion": "Memorial de Recurso de Apelación",
}

# Piezas de entrada institucionales (taxonomía A): llegan con el expediente,
# no son obra personal. Al cargarlas quedan `publicado` aunque vengan
# `privado` (cargar_obra fuerza el upgrade, nunca downgrade de global).
TIPOS_ENTRADA: set[str] = {
    "sentencia",
    "acta_audiencia",
    "oficio_elevacion",
    "auto_interlocutorio",
    "memorial_apelacion",
}


def es_pieza_entrada(tipo_documento: str) -> bool:
    """True si el tipo es pieza institucional de entrada (taxonomía A)."""
    return tipo_documento.lower() in TIPOS_ENTRADA


def faltantes(tipo_proceso: str, tipos_subidos: set[str]) -> set[str]:
    """Tipos requeridos que aún no están entre los subidos."""
    requeridos = REQUISITOS.get(tipo_proceso)
    if requeridos is None:
        raise ValueError(f"tipo_proceso desconocido: {tipo_proceso}")
    # Normaliza a lower para tolerar mayúsculas del FormData
    subidos_norm = {t.lower() for t in tipos_subidos}
    return {r for r in requeridos if r.lower() not in subidos_norm}


def nombres_legibles(tipos: set[str]) -> list[str]:
    """Nombres humanos ordenados alfabéticamente para el alert."""
    return sorted(NOMBRES.get(t, t) for t in tipos)
