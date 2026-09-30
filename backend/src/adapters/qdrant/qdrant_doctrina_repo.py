"""Repositorio vectorial de doctrina académica en Qdrant.

Colección SEPARADA `doctrina` (ficha N3, niveles-corpus): libros y obras
académicas. No se mezcla con `corpus_juridico` (leyes), `jurisprudencia`
(SCP/CIDH) ni obrados: misma configuración HNSW heredada.

Payload propio N3 además del base: `autor`, `obra`, `pagina`, `seccion`,
`nivel_autoridad=orientativa`.
"""

from __future__ import annotations

from qdrant_client import models

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo


class QdrantDoctrinaRepo(QdrantCorpusRepo):
    """Colección `doctrina` para N3 (libros académicos)."""

    COLLECTION_NAME = "doctrina"

    def _create_payload_indexes(self) -> None:
        """Índices base + claves N3 para filtros y citas."""
        super()._create_payload_indexes()
        for field, schema in (
            ("autor", models.PayloadSchemaType.KEYWORD),
            ("obra", models.PayloadSchemaType.KEYWORD),
            ("bloque", models.PayloadSchemaType.KEYWORD),
            ("nivel_autoridad", models.PayloadSchemaType.KEYWORD),
        ):
            self._client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
