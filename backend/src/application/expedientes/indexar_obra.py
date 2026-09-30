"""Caso de uso: indexar una obra formal del expediente en Qdrant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.embedder import Embedder
from src.application.ports.fragmento_repo import FragmentoRepo
from src.application.ports.obra_repo import ObraRepo
from src.domain.entities.fragmento import Fragmento
from src.domain.entities.obra import Obra
from src.domain.services.categoria_fuente import tipo_fuente_de_obra


@dataclass(frozen=True, slots=True)
class IndexarObraResponse:
    """Resultado de la indexación vectorial de una obra."""

    obra_id: int
    fragmentos_creados: int
    vectores_indexados: int


class IndexarObra:
    """Fragmenta, vectoriza y persiste una obra formal del expediente.

    La colección es compartida. El aislamiento se realiza mediante payload:
    expediente, propietario y visibilidad. Esto evita una colección por caso.
    """

    def __init__(
        self,
        obra_repo: ObraRepo,
        fragmento_repo: FragmentoRepo,
        embedder: Embedder,
        vector_repo: CorpusRepoVectorial,
        *,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> None:
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size debe ser positivo y overlap menor que chunk_size")
        self._obra_repo = obra_repo
        self._fragmento_repo = fragmento_repo
        self._embedder = embedder
        self._vector_repo = vector_repo
        self._chunk_size = chunk_size
        self._overlap = overlap

    async def ejecutar(self, obra: Obra) -> IndexarObraResponse:
        """Indexa una obra ya extraída y deja estado fallido si algo falla."""
        if obra.id is None:
            raise ValueError("La obra debe estar persistida antes de indexarse")
        # Criterio del Vocal: es instruccion de comportamiento que se inyecta
        # al prompt via {{criterio_vocal}} (ver generar_borrador), NO una fuente
        # RAG. No vectorizarlo evita que aparezca citado como doctrina/juris.
        # Se mantiene la Obra en PG (visible en listar_criterios), solo se
        # saltea el upsert a Qdrant.
        if obra.tipo_documento == "criterio":
            return IndexarObraResponse(
                obra_id=obra.id,
                fragmentos_creados=0,
                vectores_indexados=0,
            )
        if not obra.contenido_texto.strip():
            await self._obra_repo.actualizar_estado_procesamiento(obra.id, "fallido")
            raise ValueError("La obra no contiene texto extraíble")

        await self._obra_repo.actualizar_estado_procesamiento(obra.id, "procesando")
        try:
            # Reindexación segura: elimina únicamente la versión anterior de
            # esta obra, sin tocar normas ni otras obras del expediente.
            await self._vector_repo.delete_by_obra(obra.id)
            await self._fragmento_repo.delete_by_obra(obra.id)
            textos = self._fragmentar(obra.contenido_texto)
            embeddings = await self._embedder.embed(textos)
            if len(embeddings) != len(textos):
                raise RuntimeError("El embedder devolvió una cantidad incorrecta de vectores")

            fragmentos: list[Fragmento] = []
            points: list[dict[str, Any]] = []
            for index, (texto, embedding) in enumerate(zip(textos, embeddings, strict=True)):
                point_id = str(uuid5(NAMESPACE_URL, f"obra/{obra.id}/chunk/{index}"))
                metadata = {
                    "tipo_chunk": "obra_ventana",
                    "chunk_index": index,
                    "tipo_documento": obra.tipo_documento,
                    "fojas_inicio": obra.fojas_inicio,
                    "fojas_fin": obra.fojas_fin,
                }
                fragmento = Fragmento(
                    id=None,
                    norma_id=None,
                    obra_id=obra.id,
                    expediente_id=obra.expediente_id,
                    qdrant_point_id=point_id,
                    texto=texto,
                    padre_ref_id=None,
                    padre_ref_key=None,
                    nivel_jerarquico=4,
                    metadatos=metadata,
                    tipo_chunk="obra_ventana",  # type: ignore[arg-type]
                )
                fragmentos.append(fragmento)
                points.append(
                    {
                        "id": point_id,
                        "vector": embedding,
                        "vector_sparse": self._sparse_vector(texto),
                        "payload": {
                            "tipo_fuente": tipo_fuente_de_obra(obra.tipo_documento),
                            "obra_id": obra.id,
                            "expediente_id": obra.expediente_id,
                            "propietario_id": obra.propietario_id,
                            "visibilidad": obra.estado_visibilidad,
                            "tipo_documento": obra.tipo_documento,
                            "fojas_inicio": obra.fojas_inicio,
                            "fojas_fin": obra.fojas_fin,
                            "texto": texto,
                            **metadata,
                        },
                    }
                )

            await self._fragmento_repo.save_many(fragmentos)
            await self._vector_repo.upsert_corpus(points)
            await self._obra_repo.actualizar_estado_procesamiento(obra.id, "completado")
        except Exception:
            await self._obra_repo.actualizar_estado_procesamiento(obra.id, "fallido")
            raise

        return IndexarObraResponse(
            obra_id=obra.id,
            fragmentos_creados=len(fragmentos),
            vectores_indexados=len(points),
        )

    def _fragmentar(self, texto: str) -> list[str]:
        """Divide texto de obra en ventanas fijas con solapamiento."""
        step = self._chunk_size - self._overlap
        return [
            texto[start : start + self._chunk_size]
            for start in range(0, len(texto), step)
            if texto[start : start + self._chunk_size].strip()
        ]

    def _sparse_vector(self, texto: str) -> dict | None:
        """Vector disperso BM25 del fragmento (Plan C C5.2).

        Solo se incluye si el vector repo soporta el named vector 'text-sparse'
        (búsqueda híbrida real). Si no, None (el upsert no lo usa).
        """
        has_sparse = getattr(self._vector_repo, "_collection_has_sparse", None)
        if has_sparse is None or not has_sparse():
            return None
        from src.application.services.hybrid_searcher import compute_bm25_sparse

        sp = compute_bm25_sparse(texto)
        return {
            "indices": list(sp.indices),
            "values": list(sp.values),
        }
