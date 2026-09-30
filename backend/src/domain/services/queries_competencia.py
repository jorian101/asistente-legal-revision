"""Domain service: QueriesCompetencia — consultas de competencia por tipo (P3).

Pure domain logic: dado el TipoRespuesta clasificado, genera consultas de
recuperacion adicionales que apuntan a la norma de competencia de la via
procesal. Corrige los gaps medidos en P0.4:

- G5 (EXP-3349): la query del usuario menciona el delito, no la competencia
  de la consulta de oficio (Art. 194 CPPM). El embedding denso NO relaciona
  "articulo 194" con el fragmento, por lo que se requiere un filtro de
  payload determinista (abreviatura + numero_articulo).
- G6 (EXP-3145/3172): la query de prescripcion recupera Ley 1970 (supletoria)
  en vez del CPM (especial). El filtro apunta a la norma especial.

Cada consulta es una tupla (query, filtros_payload):
- query: texto para el embedding denso (semantico, ayuda a ordenar).
- filtros_payload: filtro determinista de payload en Qdrant
  (abreviatura, numero_articulo) que garantiza recuperar el articulo exacto
  aunque el score denso sea bajo. Los resultados de competencia se fusionan
  SIN umbral de score (son recuperacion explicita, no semantica).

Sin I/O, sin DI. Testable puro.
"""

from __future__ import annotations

from src.domain.value_objects.contexto_recuperado import TipoRespuesta

# (query_embedding, filtros_payload) por tipo de respuesta.
_QUERIES_POR_TIPO: dict[TipoRespuesta, tuple[tuple[str, dict], ...]] = {
    "auto_vista_consulta": (
        (
            "consulta de oficio remision de la sentencia no apelada "
            "articulo 194 codigo de procedimiento penal militar",
            {"abreviatura": "CPPM", "numero_articulo": 194},
        ),
        (
            "competencia de la sala de apelaciones y consulta consulta de oficio "
            "articulo 43 ley de organizacion judicial militar",
            {"abreviatura": "LOJM", "numero_articulo": 43},
        ),
    ),
    "auto_vista_apelacion_incidental": (
        (
            "apelacion incidental contra resolucion interlocutoria competencia "
            "de la sala de apelaciones y consulta articulo 43 ley de organizacion "
            "judicial militar",
            {"abreviatura": "LOJM", "numero_articulo": 43},
        ),
        (
            "prescripcion de la accion penal militar interrupcion articulos 38 40 "
            "44 45 codigo penal militar",
            {"abreviatura": "CPM"},
        ),
    ),
    "dictamen_radicatoria_consulta": (
        (
            "dictamen de radicatoria consulta de oficio articulo 63 numero 1 "
            "ley de organizacion judicial militar",
            {"abreviatura": "LOJM", "numero_articulo": 63},
        ),
    ),
    "dictamen_radicatoria_apelacion": (
        (
            "dictamen de radicatoria en apelacion articulo 63 numero 1 ley de "
            "organizacion judicial militar",
            {"abreviatura": "LOJM", "numero_articulo": 63},
        ),
    ),
    "consulta_simple": (),
}


def queries_competencia(tipo_respuesta: TipoRespuesta) -> tuple[tuple[str, dict], ...]:
    """Devuelve consultas (query, filtros_payload) de competencia por tipo.

    Vacio para consulta_simple (no genera borrador, no requiere competencia).

    Raises:
        KeyError: si el tipo no esta mapeado (defensivo).
    """
    return _QUERIES_POR_TIPO[tipo_respuesta]


__all__ = ["queries_competencia"]
