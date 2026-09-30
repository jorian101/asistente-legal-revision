"""Adapter: Qdrant Corpus Repo — Persistencia vectorial en Qdrant.

Implementa puerto application.ports.CorpusRepoVectorial.
Usa qdrant-client HTTP + payload indexes para filtros rápidos.
"""

from __future__ import annotations

import asyncio
import logging

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.config import get_settings
from src.domain.value_objects import ScoredPoint, SparseVector

log = logging.getLogger(__name__)


class QdrantCorpusRepo(CorpusRepoVectorial):
    """Repositorio vectorial del corpus jurídico en Qdrant.

    Colección compartida: 'corpus_juridico'. Normas y obras se distinguen por
    `tipo_fuente` y se aíslan con filtros de payload.
    - vectors: size=embedding_dim, distance=Cosine
    - payload indexes: abreviatura, numero_articulo, tipo_chunk, nivel_jerarquico, norma_id
    - on_disk_payload: True (ahorra RAM)
    - quantization: scalar (ahorra 75% RAM)
    """

    COLLECTION_NAME = "corpus_juridico"
    SPARSE_VECTOR_NAME = "text-sparse"

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        embedding_dim: int | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        settings = get_settings()
        self._url = url or settings.qdrant_url
        self._api_key = api_key or settings.qdrant_api_key
        self._dim = embedding_dim or settings.embedding_dim
        self._client = client or QdrantClient(url=self._url, api_key=self._api_key)
        self._sparse_checked = False
        self._sparse_present = False

    async def ensure_collection(self) -> None:
        """Crea la colección si no existe con configuración óptima."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_collection_sync)

    def _ensure_collection_sync(self) -> None:
        existing = self._client.get_collections().collections
        names = {c.name for c in existing}
        if self.COLLECTION_NAME not in names:
            self._create_collection()
            return

        # Existe: verificar dimension
        info = self._client.get_collection(self.COLLECTION_NAME)
        current_dim = info.config.params.vectors.size
        if current_dim == self._dim:
            # Qdrant no permite agregar un named sparse vector a una colección
            # existente mediante update_collection. Mantener el índice denso
            # actual y crear solo payload indexes; la migración sparse requiere
            # una colección nueva y reindexación explícita.
            self._ensure_sparse_and_indexes()
            return

        # Mismatch: operacion destructiva. Bloqueada por defecto para evitar
        # borrado accidental de 3109 vectores.
        settings = get_settings()
        if not settings.safety_allow_collection_recreate:
            raise RuntimeError(
                f"Dimension mismatch en Qdrant: actual={current_dim} "
                f"deseada={self._dim} (coleccion '{self.COLLECTION_NAME}'). "
                f"Recreacion BLOQUEADA por SAFETY_ALLOW_COLLECTION_RECREATE=false. "
                f"Para migrar el modelo de embedding, setea "
                f"SAFETY_ALLOW_COLLECTION_RECREATE=1 y reejecuta la ingesta."
            )

        log.warning(
            "dimension mismatch en Qdrant: actual=%s deseada=%s — recreando coleccion '%s'",
            current_dim,
            self._dim,
            self.COLLECTION_NAME,
        )
        self._client.delete_collection(self.COLLECTION_NAME)
        self._create_collection()

    def crear_coleccion(self) -> None:
        """Crea la coleccion con el esquema completo (denso + sparse + indices de payload).

        Fuente unica del esquema: la usan `ensure_collection` y las migraciones.
        """
        self._create_collection()

    def _create_collection(self) -> None:
        """Crea la coleccion con la dim configurada (asume que no existe)."""
        self._client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=self._dim,
                distance=models.Distance.COSINE,
            ),
            sparse_vectors_config={
                self.SPARSE_VECTOR_NAME: models.SparseVectorParams(),
            },
            on_disk_payload=True,
            hnsw_config=models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
            ),
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            ),
        )

        self._create_payload_indexes()

    def _create_payload_indexes(self) -> None:
        """Crea los payload indexes para filtros rapidos (idempotente)."""
        for field, schema in (
            ("abreviatura", models.PayloadSchemaType.KEYWORD),
            ("tipo_chunk", models.PayloadSchemaType.KEYWORD),
            ("numero_articulo", models.PayloadSchemaType.INTEGER),
            ("nivel_jerarquico", models.PayloadSchemaType.INTEGER),
            ("norma_id", models.PayloadSchemaType.INTEGER),
            ("tipo_fuente", models.PayloadSchemaType.KEYWORD),
            ("obra_id", models.PayloadSchemaType.INTEGER),
            ("expediente_id", models.PayloadSchemaType.INTEGER),
            ("tipo_documento", models.PayloadSchemaType.KEYWORD),
            # Regla 4: filtrado de visibilidad de obrados.
            ("visibilidad", models.PayloadSchemaType.KEYWORD),
            ("propietario_id", models.PayloadSchemaType.INTEGER),
        ):
            self._client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )

    def _ensure_sparse_and_indexes(self) -> None:
        """Garantiza sparse vectors e indices de privacidad sin recrear.

        Sprint 3 (D1): la coleccion ya existe con 3109 puntos densos. No se
        recrea (perderia los vectores). Se agrega el sparse vector y los
        payload indexes 'visibilidad'/'propietario_id' si no estan presentes.
        Qdrant permite `update_collection` para agregar sparse_vectors_config
        y `create_payload_index` es idempotente por campo.
        """
        # Sparse vector solo se configura al crear una colección nueva. Qdrant
        # rechaza agregar un nombre de vector inexistente a una colección que
        # ya contiene puntos, por lo que no se intenta una migración implícita.
        params = self._client.get_collection(self.COLLECTION_NAME).config.params
        if not getattr(params, "sparse_vectors", None):
            log.info(
                "Coleccion '%s' sin sparse vectors; se mantiene fallback dense",
                self.COLLECTION_NAME,
            )

        # Indices de privacidad (create_payload_index es idempotente).
        for field, schema in (
            ("visibilidad", models.PayloadSchemaType.KEYWORD),
            ("propietario_id", models.PayloadSchemaType.INTEGER),
            ("tipo_fuente", models.PayloadSchemaType.KEYWORD),
            ("obra_id", models.PayloadSchemaType.INTEGER),
            ("expediente_id", models.PayloadSchemaType.INTEGER),
            ("tipo_documento", models.PayloadSchemaType.KEYWORD),
        ):
            self._client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )

    async def upsert_corpus(self, points: list[dict]) -> None:
        """Inserta/actualiza puntos vectoriales en lote.

        Args:
            points: Lista de dicts con:
                - id: UUIDv4 string (qdrant_point_id del Fragmento)
                - vector: list[float] de dimensión embedding_dim
                - payload: dict con campos:
                    * norma_id: int
                    * abreviatura: str (ej: 'CPPM')
                    * numero_articulo: int
                    * texto: str
                    * tipo_chunk: str
                    * nivel_jerarquico: int
                    * padre_ref_key: str | None
                    * metadatos: dict | None
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._upsert_corpus_sync, points)

    def _upsert_corpus_sync(self, points: list[dict]) -> None:
        """Inserta/actualiza puntos en Qdrant (parte sincrona del upsert).

        Particiona en batches de `Settings.qdrant_upsert_batch_size` puntos
        (default 256, empirico Sprint 0: con 1363 puntos de CPE en un solo
        request, el cliente HTTP de Qdrant sin timeout default colgaba).

        Plan C (C5.2): si un punto trae `vector_sparse` (dict con indices y
        values), se empaqueta como named vector denso + `text-sparse`.
        """
        qdrant_points = []
        for p in points:
            if p.get("vector_sparse") is not None:
                qdrant_points.append(
                    models.PointStruct(
                        id=p["id"],
                        vector={
                            "": p["vector"],
                            self.SPARSE_VECTOR_NAME: models.SparseVector(
                                indices=p["vector_sparse"]["indices"],
                                values=p["vector_sparse"]["values"],
                            ),
                        },
                        payload=p["payload"],
                    )
                )
            else:
                qdrant_points.append(
                    models.PointStruct(
                        id=p["id"],
                        vector=p["vector"],
                        payload=p["payload"],
                    )
                )
        batch_size = get_settings().qdrant_upsert_batch_size
        for i in range(0, len(qdrant_points), batch_size):
            self._client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=qdrant_points[i : i + batch_size],
                wait=True,
            )

    async def delete_by_norma(self, norma_id: int) -> None:
        """Elimina todos los puntos de una norma por ID."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="norma_id",
                                match=models.MatchValue(value=norma_id),
                            )
                        ]
                    )
                ),
                wait=True,
            ),
        )

    async def actualizar_visibilidad_obra(self, obra_id: int, visibilidad: str) -> None:
        """Actualiza el payload `visibilidad` de los puntos de una obra."""
        await self.actualizar_payload_obra(obra_id, {"visibilidad": visibilidad})

    async def actualizar_payload_obra(self, obra_id: int, payload: dict) -> None:
        """Actualiza campos del payload de todos los puntos de una obra."""
        await self._set_payload_por("obra_id", obra_id, payload)

    async def actualizar_payload_norma(self, norma_id: int, payload: dict) -> None:
        """Actualiza campos del payload de todos los puntos de una norma/fuente."""
        await self._set_payload_por("norma_id", norma_id, payload)

    async def _set_payload_por(self, clave: str, valor: int, payload: dict) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.set_payload(
                collection_name=self.COLLECTION_NAME,
                payload=payload,
                points=models.Filter(
                    must=[models.FieldCondition(key=clave, match=models.MatchValue(value=valor))]
                ),
                wait=True,
            ),
        )

    async def delete_by_obra(self, obra_id: int) -> None:
        """Elimina puntos vectoriales asociados a una obra."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="obra_id",
                                match=models.MatchValue(value=obra_id),
                            )
                        ]
                    )
                ),
                wait=True,
            ),
        )

    async def list_all_ids(self) -> list[str]:
        """Scroll de todos los IDs activos en la coleccion corpus_juridico.

        Usa scroll() sin filtro: streaming via puntos con payload minimo (id solo).
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._scroll_all_ids_sync)

    def _scroll_all_ids_sync(self) -> list[str]:
        ids: list[str] = []
        offset: models.PointId | None = None
        limit = 1000
        while True:
            records, next_offset = self._client.scroll(
                collection_name=self.COLLECTION_NAME,
                limit=limit,
                offset=offset,
                with_vectors=False,
                with_payload=False,
            )
            ids.extend(str(r.id) for r in records)
            if next_offset is None:
                break
            offset = next_offset
        return ids

    async def delete_many(self, ids: list[str]) -> None:
        """Elimina múltiples puntos por ID en batch."""
        if not ids:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._delete_many_sync, ids)

    def _delete_many_sync(self, ids: list[str]) -> None:
        for i in range(0, len(ids), 500):
            self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=models.PointIdsList(
                    points=ids[i : i + 500],
                ),
                wait=True,
            )

    def close(self) -> None:
        """Cierra el cliente Qdrant (se llama al apagar el proceso)."""
        self._client.close()

    # ----------------------------------------------------------------------
    # Busqueda hibrida (Sprint 3, D1) + Regla 4 (privacidad obligatoria)
    # ----------------------------------------------------------------------

    def _apply_required_filters(self, filters: dict, usuario_id: int) -> models.Filter:
        """Convierte filtros dict + usuario_id a Filter Qdrant plano.

        Regla 4 BLOQUEANTE: `usuario_id` es OBLIGATORIO. Si no esta -> ValueError
        (defensa en profundidad; el service tambien lo exige).

        Devuelve un unico filtro con:
        - `must`: restricciones de dominio explicitas (norma_id, ...).
        - `should`: condiciones de privacidad (Regla 4) con OR.
        """
        must: list[models.Condition] = []

        norma_id = filters.get("norma_id")
        if norma_id is not None:
            must.append(
                models.FieldCondition(key="norma_id", match=models.MatchValue(value=norma_id))
            )

        abreviatura = filters.get("abreviatura")
        if abreviatura is not None:
            must.append(
                models.FieldCondition(key="abreviatura", match=models.MatchValue(value=abreviatura))
            )

        numero_articulo = filters.get("numero_articulo")
        if numero_articulo is not None:
            try:
                numero_articulo = int(numero_articulo)
            except (TypeError, ValueError) as exc:
                raise ValueError("numero_articulo debe ser un entero") from exc
            must.append(
                models.FieldCondition(
                    key="numero_articulo", match=models.MatchValue(value=numero_articulo)
                )
            )

        expediente_id = filters.get("expediente_id")
        if expediente_id is not None:
            try:
                expediente_id = int(expediente_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("expediente_id debe ser un entero") from exc
            # Plan C (C1.2): la doctrina global (expediente_id NULL) se
            # recupera SIEMPRE, además de las obras del expediente. Un must
            # estricto la excluiría. Se usa un sub-filtro OR:
            #   expediente_id = X  OR  expediente_id IS NULL
            #
            # Excepcion (solo_expediente, Regla 5): en generacion de borradores
            # el pipeline marca solo_expediente=True y el filtro es estricto —
            # los ANTECEDENTES se redactan unicamente de los obrados del caso.
            if filters.get("solo_expediente"):
                must.append(
                    models.FieldCondition(
                        key="expediente_id",
                        match=models.MatchValue(value=expediente_id),
                    )
                )
            else:
                must.append(
                    models.Filter(
                        should=[
                            models.FieldCondition(
                                key="expediente_id",
                                match=models.MatchValue(value=expediente_id),
                            ),
                            models.IsNullCondition(
                                is_null=models.PayloadField(key="expediente_id")
                            ),
                        ]
                    )
                )

        obra_ids = filters.get("obra_ids")
        if obra_ids is not None:
            # Filtro por obras seleccionadas en el chat (selector con todas
            # marcadas por defecto). Regla 5: el expediente_id ya restringe;
            # este filtro acota a las obras elegidas.
            try:
                ids = [int(i) for i in obra_ids]
            except (TypeError, ValueError) as exc:
                raise ValueError("obra_ids debe ser una lista de enteros") from exc
            if ids:
                must.append(
                    models.FieldCondition(
                        key="obra_id",
                        match=models.MatchAny(any=ids),
                    )
                )

        tipo_fuente = filters.get("tipo_fuente")
        if tipo_fuente is not None:
            must.append(
                models.FieldCondition(
                    key="tipo_fuente",
                    match=models.MatchValue(value=tipo_fuente),
                )
            )

        return models.Filter(
            must=must,
            should=self._privacy_conditions(usuario_id),
            # Criterio del Vocal (instruccion de comportamiento, inyectada al
            # prompt, no fuente RAG): nunca debe salir citada como doctrina.
            must_not=[
                models.FieldCondition(
                    key="tipo_documento",
                    match=models.MatchValue(value="criterio"),
                )
            ],
        )

    def _privacy_conditions(self, usuario_id: int) -> list[models.Condition]:
        """Condiciones de privacidad (Regla 4): un operador ve solo fragmentos
        que matcheen al menos una de:
        - `visibilidad` NO definida (corpus juridico / normas publicas),
        - `visibilidad` == 'publicado' (obras publicadas),
        - `visibilidad` == 'global' (doctrina global — visible para cualquier
          usuario autenticado, sin depender del propietario; Plan C C1.1),
        - `propietario_id` == usuario_id (obras privadas propias).

        Excluye obras privadas cuyo propietario es otro (no matchea ninguna).
        Qdrant interpreta un `should` (lista) como OR con al menos uno.
        """
        return [
            models.IsEmptyCondition(is_empty=models.PayloadField(key="visibilidad")),
            models.FieldCondition(
                key="visibilidad",
                match=models.MatchValue(value="publicado"),
            ),
            models.FieldCondition(
                key="visibilidad",
                match=models.MatchValue(value="global"),
            ),
            models.FieldCondition(
                key="propietario_id",
                match=models.MatchValue(value=usuario_id),
            ),
        ]

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        alpha: float,
        filters: dict,
        limit: int,
    ) -> list[ScoredPoint]:
        """Busqueda híbrida (denso + disperso) con RRF server-side.

        Regla 4: `usuario_id` en filters es OBLIGATORIO (ValueError si falta).
        """
        usuario_id = filters.get("usuario_id")
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool) or usuario_id <= 0:
            raise ValueError(
                "usuario_id es obligatorio en search_hybrid (Regla 4): "
                "int > 0, no bool. El filtro de privacidad nunca es opcional."
            )

        if not self._collection_has_sparse():
            # ponytail: el corpus ingerido solo tiene denso (no reindexado con
            # sparse). Degradar a denso en vez de fallar el RRF. Reintroducir
            # el canal sparse cuando se reindexe el corpus con BM25/SPLADE.
            log.warning(
                "search_hybrid: coleccion sin sparse vectors '%s'. Degradando a busqueda densa.",
                self.SPARSE_VECTOR_NAME,
            )
            return await self.search_dense(
                dense_vector=dense_vector,
                filters=filters,
                limit=limit,
            )

        qdrant_filter = self._apply_required_filters(filters, usuario_id)

        alpha = float(alpha)  # reservado: RRF puro por ahora (D7)

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._query_points_hybrid(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    qdrant_filter=qdrant_filter,
                    limit=limit * 2,
                    prefetch_limit=limit * 2,
                ),
            )
        except UnexpectedResponse as exc:
            return self._sin_coleccion(exc)
        # La fusion RRF empata seguido en el corte (mismo puesto en listas distintas) y Qdrant
        # desempata distinto en cada corrida: la misma consulta traia obras distintas. Se pide
        # el doble y se corta aca, desempatando por id.
        puntos = sorted(self._to_scored_points(result), key=lambda p: (-p.score, p.qdrant_id))
        return puntos[:limit]

    def _sin_coleccion(self, exc: UnexpectedResponse) -> list[ScoredPoint]:
        """404 = la coleccion aun no existe (jurisprudencia/doctrina sin ingerir): 0 resultados."""
        if exc.status_code != 404:
            raise exc
        log.warning("coleccion '%s' inexistente: sin resultados", self.COLLECTION_NAME)
        return []

    async def search_dense(
        self,
        dense_vector: list[float],
        filters: dict,
        limit: int,
    ) -> list[ScoredPoint]:
        """Busqueda k-NN densa (fallback cuando no hay sparse vectors)."""
        usuario_id = filters.get("usuario_id")
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool) or usuario_id <= 0:
            raise ValueError(
                "usuario_id es obligatorio en search_dense (Regla 4): "
                "int > 0, no bool. El filtro de privacidad nunca es opcional."
            )

        qdrant_filter = self._apply_required_filters(filters, usuario_id)

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._client.query_points(
                    collection_name=self.COLLECTION_NAME,
                    query=dense_vector,
                    query_filter=qdrant_filter,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                ),
            )
        except UnexpectedResponse as exc:
            return self._sin_coleccion(exc)
        return self._to_scored_points(result)

    def _query_points_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        qdrant_filter: models.Filter,
        limit: int,
        prefetch_limit: int,
    ) -> models.QueryResponse:
        """Query híbrida con prefetch denso + disperso y fusión RRF (sync)."""
        dense_prefetch = models.Prefetch(
            query=dense_vector,
            using="",  # vector denso default (coleccion con un solo vectors)
            filter=qdrant_filter,
            limit=prefetch_limit,
        )
        sparse_prefetch = models.Prefetch(
            query=models.SparseVector(
                indices=list(sparse_vector.indices),
                values=list(sparse_vector.values),
            ),
            using=self.SPARSE_VECTOR_NAME,
            filter=qdrant_filter,
            limit=prefetch_limit,
        )
        return self._client.query_points(
            collection_name=self.COLLECTION_NAME,
            prefetch=[dense_prefetch, sparse_prefetch],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

    @staticmethod
    def _to_scored_points(result: models.QueryResponse) -> list[ScoredPoint]:
        """Convierte la respuesta de Qdrant a list[ScoredPoint]."""
        points: list[ScoredPoint] = []
        for hit in getattr(result, "points", []):
            points.append(
                ScoredPoint(
                    qdrant_id=str(hit.id),
                    score=float(hit.score),
                    payload=hit.payload or {},
                )
            )
        return points

    def _collection_has_sparse(self) -> bool:
        """True si la coleccion tiene configurado el sparse vector (cacheado).

        El check es idempotente: el resultado se cachea porque la config de la
        coleccion no cambia en runtime. Si el sparse se agrega luego (reindexado
        BM25), un restart del proceso lo detecta.
        """
        if self._sparse_checked:
            return self._sparse_present
        try:
            params = self._client.get_collection(self.COLLECTION_NAME).config.params
            self._sparse_present = bool(getattr(params, "sparse_vectors", None))
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                return False  # no existe aun: sin cachear, para detectarla al crearse
            self._sparse_present = False
        except Exception:  # noqa: BLE001 — degradar a denso si Qdrant no responde
            self._sparse_present = False
        self._sparse_checked = True
        return self._sparse_present

    def fusion_enabled(self) -> bool:
        """True si `search_hybrid` usara fusion RRF (coleccion con sparse).

        Expuesto para que HybridSearcher sepa si los scores son de coseno
        (degrade a denso -> umbral aplicable) o de rank-fusion RRF (~0-0.5,
        no comparables al umbral de similitud -> no umbralizar). Mismo valor
        cacheado que usa search_hybrid para decidir su camino.
        """
        return self._collection_has_sparse()
