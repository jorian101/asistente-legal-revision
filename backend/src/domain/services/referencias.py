"""Servicio: referencias legibles para display de citas y breadcrumbs.

Las claves de segmentacion internas (padre_ref_key tipo 'LOJM_3_MASTER')
no deben llegar al LLM ni al frontend crudas: el modelo las cita como si
fueran normas y la UI muestra tokens tecnicos. Solo DISPLAY — el valor
original en payload/BD no se modifica.
"""

from __future__ import annotations

_SUFIJOS_REF_INTERNOS = ("_MASTER", "_HIJO")


def etiqueta_legible(ref: str) -> str:
    """Convierte una referencia interna en etiqueta legible.

    'LOJM_3_MASTER' -> 'LOJM 3'; 'CPPM_184_HIJO' -> 'CPPM 184'.
    Claves sin sufijos quedan igual salvo guiones bajos -> espacios.
    """
    etiqueta = ref
    for sufijo in _SUFIJOS_REF_INTERNOS:
        if etiqueta.endswith(sufijo):
            etiqueta = etiqueta[: -len(sufijo)]
            break
    return etiqueta.replace("_", " ").strip()
