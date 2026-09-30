"""Repositorio vectorial de jurisprudencia vinculante en Qdrant.

Colección SEPARADA `jurisprudencia` (ficha N2, niveles-corpus): SCP del
TCP y fallos de la Corte IDH. No se mezcla con `corpus_juridico` (leyes)
ni con obrados: distinta colección, mismos vectores/cofiguración HNSW
(heredados de QdrantCorpusRepo).

Payload propio N2 además del base: `numero_sentencia`, `organo`,
`bloque` (hecho/derecho/fallo), `nivel_autoridad=vinculante`.
"""

from __future__ import annotations

from qdrant_client import models

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo


class QdrantJurisprudenciaRepo(QdrantCorpusRepo):
    """Colección `jurisprudencia` para N2 (SCP + Corte IDH)."""

    COLLECTION_NAME = "jurisprudencia"

    def _create_payload_indexes(self) -> None:
        """Índices base + claves N2 para filtros (numero, órgano, bloque)."""
        super()._create_payload_indexes()
        for field, schema in (
            ("numero_sentencia", models.PayloadSchemaType.KEYWORD),
            ("organo", models.PayloadSchemaType.KEYWORD),
            ("bloque", models.PayloadSchemaType.KEYWORD),
            ("nivel_autoridad", models.PayloadSchemaType.KEYWORD),
        ):
            self._client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
