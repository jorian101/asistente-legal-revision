"""Entidad de dominio Fragmento.

Un Fragmento es la unidad atomica del corpus indexado: cada articulo, numeral,
paragrafo o inciso de una norma se persiste como un Fragmento. Algunos
fragmentos son `indexables` (van a Qdrant con vector + payload) y otros son
`estructurales` (solo context para expansion jerarquica, no vectorizados).

Regla Clean Architecture: dataclass pura (3.13 `slots=True`). El ORM vive en
adapters/postgres/models/fragmento.py.

Diseño del self-ref padre: en PostgreSQL es FK BIGINT a fragmento.id
(`padre_ref_id`). En Qdrant el payload lleva el string semantico
(`padre_ref_key`, ej: 'CPPM_184_MASTER') para que el payload sea legible
y resistente a re-indexaciones fuera de la app.

Esquema (arquitectura.md seccion 3.1, tabla `fragmento`):
- id BIGINT PK
- norma_id BIGINT NULL REFERENCES norma(id) ON DELETE CASCADE
- obra_id BIGINT NULL REFERENCES obra(id) ON DELETE CASCADE
- expediente_id BIGINT NULL REFERENCES expediente(id) ON DELETE CASCADE
- qdrant_point_id TEXT NOT NULL UNIQUE (UUIDv4)
- texto TEXT NOT NULL
- padre_ref_id BIGINT NULL REFERENCES fragmento(id)   (self-ref)
- padre_ref_key TEXT NULL                              (string semantico)
- nivel_jerarquico INT NULL CHECK (0..4)
- metadatos JSONB NULL
- CHECK ((norma_id IS NOT NULL) OR (obra_id IS NOT NULL))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NivelJerarquico = Literal[0, 1, 2, 3, 4]
"""
0 = raiz (no persistido como tal; la primera fila es el nivel 1)
1 = parte / libro / seccion raiz (estructura de nivel superior)
2 = titulo / titulo unico (estructura intermedia)
3 = capitulo / seccion (estructura intermedia-baja)
4 = articulo / paragrafo / numeral / inciso (unidad minima)
"""

#: Tipos de chunk que produce cualquier estrategia de segmentacion.
#: Ver domain/services/segmentacion para el detalle por norma.
TipoChunk = Literal[
    # Estructurales (no se envian a Qdrant como vector; quedan como contexto)
    "estructura_padre",
    "estructura_parte",
    "estructura_libro",
    "estructura_seccion",
    "estructura_titulo",
    "estructura_capitulo",
    "estructura_sub_padre",
    # Indexables — normativas
    "articulo_simple",
    "articulo_multiparagrafo",
    "numeral_autonomo",
    "subnumeral_autonomo",
    "inciso_autonomo",
    "parrafo_autonomo",
    "parrafo_principal",
    "regla_complementaria_funcional",
    "regla_excepcion",
    "agravante",
    "facultad_procesal",
    "regla_obligacion",
    "competencia_jurisdiccional",
    "obligacion_funcional",
    "atribucion_estrategica",
    "atribucion_mando",
    "atribucion_territorial_operativa",
    "derecho_especifico",
    "categoria_derechos",
    # Indexables - obras formales de expedientes
    "obra_ventana",
    # Indexables — jurisprudencia
    "fundamento_de_hecho",
    "fundamento_de_derecho_planteamiento",
    "fundamento_de_derecho_doctrina",
    "fundamento_de_derecho_analisis",
    "fundamentacion_del_fallo",
]


@dataclass(slots=True)
class Fragmento:
    """Fragmento del corpus juridico (atomo indexable o estructural).

    Atributos:
        id: PK interno. None antes de persistir.
        norma_id: FK a norma cuando el fragmento pertenece al corpus
            juridico cargado por el admin. None si pertenece a una obra.
        obra_id: FK a obra (pieza procesal del expediente). None para
            corpus juridico. Exactly-one de (norma_id, obra_id) debe ser
            no-None (check en DB).
        expediente_id: FK a expediente cuando el fragmento proviene de una
            obra cargada por un operador. None para corpus juridico.
        qdrant_point_id: UUIDv4 que identifica el punto en Qdrant. Solo los
            fragmentos `indexables` lo tendran efectivamente apuntando a un
            point; los `estructurales` quedan con string vacio o None.
        texto: Contenido textual del fragmento (lo que se vectoriza para
            los indexables).
        padre_ref_id: FK a fragmento.id (self-ref). El ID de PostgreSQL
            del fragmento padre (chunk estructural o maestro).
        padre_ref_key: String semantico del padre (ej: 'CPPM_184_MASTER').
            Se persiste tambien en el payload de Qdrant para evitar
            acoplarse al ID interno si la coleccion se reindexa.
        nivel_jerarquico: 0..4 (ver NivelJerarquico).
        metadatos: JSON libre (tema, funcion, actores, notas, etc.).
            Para indexables: los campos relevantes se duplican al payload
            de Qdrant para habilitar filtros.
        tipo_chunk: Forma textual del fragmento (TipoChunk). Vive en
            `metadatos['tipo_chunk']` para no agregar columna a la DB.
            Helper provisto: set_tipo_chunk / get_tipo_chunk.
    """

    id: int | None
    norma_id: int | None
    obra_id: int | None
    expediente_id: int | None
    qdrant_point_id: str
    texto: str
    padre_ref_id: int | None
    padre_ref_key: str | None
    nivel_jerarquico: NivelJerarquico | None
    metadatos: dict[str, Any] | None
    tipo_chunk: TipoChunk

    # -------- helpers ------------------------------------------------------
    @property
    def es_indexable(self) -> bool:
        """Un fragmento indexable tiene un qdrant_point_id no vacio."""
        return bool(self.qdrant_point_id)
