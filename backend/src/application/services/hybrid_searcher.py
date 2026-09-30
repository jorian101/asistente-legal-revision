"""Servicio: HybridSearcher — Fase 2 del pipeline RAG (Sprint 3).

Embe la query, llama a Qdrant hybrid (RRF server-side), hidrata fragmentos
desde PostgreSQL y los retorna con score.

Regla 4 Trail of Bits BLOQUEANTE: `usuario_id` es OBLIGATORIO en todo el
flujo. Si se llama sin el -> TypeError en runtime (sin default).
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import TYPE_CHECKING

from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects import SparseVector

if TYPE_CHECKING:
    from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo
    from src.application.ports.corpus_vectorial import CorpusRepoVectorial
    from src.application.ports.embedder import Embedder
    from src.application.ports.fragmento_repo import FragmentoRepo


# Tamanio del espacio disperso (indice maximo posible en Qdrant sparse).
# 2^24 = 16.7M indices unicos, suficiente para hash de tokens.
_SPARSE_DIM = 1 << 24

_TOKENIZER = re.compile(r"[a-z0-9]+")

# Palabras vacias del castellano (sin tilde: se comparan tras normalizar). Sin quitarlas,
# el producto punto lo ganaba el fragmento con mas "de la que el".
# Constante k de RRF (Cormack et al.); el mismo 60 que usa Qdrant por defecto.
_RRF_K = 60

_STOPWORDS = frozenset(
    "a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque cada como "  # noqa: SIM905
    "con contra cual cuales cuando de del desde donde durante e el ella ellas ellos en entre "
    "era eran es esa esas ese eso esos esta estan estar estas este esto estos fue fueron ha "
    "han hasta hay la las le les lo los mas me mi mis mucho muy ni no nos nosotros o os otra "
    "otras otro otros para pero poco por porque que quien quienes se sea sean ser si sin "
    "sobre son su sus tambien tanto te ti tu tus un una unas uno unos y ya yo".split()
)


def _normalizar(texto: str) -> str:
    """Minusculas y sin tildes: 'Detención' y 'detencion' son el mismo termino."""
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def compute_bm25_sparse(text: str) -> SparseVector:
    """Vector lexico disperso: token -> indice hash, valor = peso del termino.

    Los indices son UNICOS (Qdrant valida sparse indices sin duplicados). El peso es
    `1 + ln(tf)` y el vector se normaliza (L2): sin la normalizacion por longitud, el
    producto punto favorecia siempre a los fragmentos mas largos (un mismo articulo
    salia entre los primeros de todas las consultas). Tokeniza sin tildes (antes
    'detencion' se partia en 'detenci' + 'n') y omite palabras vacias.

    NOTA: sigue siendo un proxy de BM25 (sin IDF); el BM25 real requiere estadisticas
    del corpus. Cambiar esta funcion cambia los vectores ya indexados: hay que
    recalcularlos (scripts/reindexar_sparse.py).
    """
    frecuencias: dict[int, int] = {}
    for token in _TOKENIZER.findall(_normalizar(text)):
        if token in _STOPWORDS:
            continue
        h = hashlib.sha256(token.encode()).digest()
        idx = int.from_bytes(h[:3], "big") % _SPARSE_DIM
        frecuencias[idx] = frecuencias.get(idx, 0) + 1
    # Orden estable por indice: mismo texto -> mismo vector siempre.
    indices = sorted(frecuencias)
    pesos = [1.0 + math.log(frecuencias[i]) for i in indices]
    norma = math.sqrt(sum(w * w for w in pesos)) or 1.0
    return SparseVector(indices=tuple(indices), values=tuple(w / norma for w in pesos))


class HybridSearcher:
    """Orquestador de la busqueda hibrida (fase 2 del pipeline RAG).

    Atributos:
        embedder: Port Embedder (vector denso de la query).
        corpus_repo: Port CorpusRepoVectorial (Qdrant).
        fragmento_repo: Port FragmentoRepo (PG).
        config: ConfiguracionRAG singleton (umbrales operativos).
    """

    def __init__(
        self,
        embedder: Embedder,
        corpus_repo: CorpusRepoVectorial,
        fragmento_repo: FragmentoRepo,
        config: ConfiguracionRAGRepo,
        jurisprudencia_repo: CorpusRepoVectorial | None = None,
        doctrina_repo: CorpusRepoVectorial | None = None,
    ) -> None:
        self._embedder = embedder
        self._corpus_repo = corpus_repo
        self._fragmento_repo = fragmento_repo
        self._config = config
        # N2 (colección `jurisprudencia`) y N3 (colección `doctrina`):
        # fan-out opcional en la query principal. None = solo
        # corpus_juridico (compat).
        self._repos_extra = [r for r in (jurisprudencia_repo, doctrina_repo) if r is not None]

    async def buscar(
        self,
        query: str,
        usuario_id: int,
        filtros: dict[str, object],
        top_k_denso: int,
        top_k_lexico: int,
        queries_extra: tuple[tuple[str, dict], ...] = (),
        con_fanout: bool = True,
    ) -> list[tuple[Fragmento, float]]:
        """Embe query (+ queries de competencia) -> busqueda hibrida -> PG.

        Args:
            query: Texto de la consulta original.
            usuario_id: OBLIGATORIO (Regla 4 — sin default; debe ser int > 0).
            filtros: Filtros de payload (ej. expediente_id, abreviatura).
            top_k_denso: Candidatos densos a recuperar por query.
            top_k_lexico: Candidatos lexicos (BM25) a recuperar por query.
            queries_extra: Consultas de competencia (P3) como tuplas
                (query, filtros_payload). Recuperan la norma de competencia
                de la via procesal que la query del usuario no menciona
                (ej. Art. 194 CPPM en consulta de oficio; prescripcion CPM
                en apelacion). Se fusionan SIN umbral de score: son
                recuperacion explicita determinada por el filtro de payload,
                no semantica.

        Returns:
            Lista de (Fragmento, score): resultados de la query principal
            (umbral score_threshold) + puntos de competencia (sin umbral),
            dedupe por qdrant_id, ordenada por score descendente.

        Raises:
            TypeError: Si usuario_id no es un int positivo (Regla 4).
        """
        # Regla 4 BLOQUEANTE (D5): defensa en profundidad contra usuario_id
        # invalido. Sin este check, un caller con bug filtraria obras ajenas.
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool) or usuario_id <= 0:
            raise TypeError(
                f"usuario_id es obligatorio y debe ser int positivo "
                f"(Regla 4 — recibido {usuario_id!r})."
            )

        cfg = await self._config.get_config()
        k = top_k_denso + top_k_lexico

        # El usuario_id en filters es OBLIGATORIO (Regla 4 — el adapter
        # tambien lo exige, defensa en profundidad).
        filtros_with_user = {**filtros, "usuario_id": usuario_id}
        query_busqueda = await self._query_de_busqueda(query, cfg)

        # Fusionar scored_points (dedupe por qdrant_id, mejor score).
        mejor_score: dict[str, float] = {}
        # qdrant_ids marcados como competencia: se fusionan SIN umbral.
        competencia_ids: set[str] = set()
        # Rankings por lista (colección o consulta) para la fusión RRF entre listas.
        listas: list[tuple[float, list[str]]] = []

        def _registrar(puntos, peso: float = 1.0) -> None:
            listas.append((peso, [sp.qdrant_id for sp in puntos]))
            for sp in puntos:
                if sp.score > mejor_score.get(sp.qdrant_id, float("-inf")):
                    mejor_score[sp.qdrant_id] = sp.score

        # 1) Query principal: con umbral score_threshold.
        dense_vector = (await self._embedder.embed([query_busqueda]))[0]
        sparse_vector = compute_bm25_sparse(query_busqueda)
        _registrar(
            await self._corpus_repo.search_hybrid(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                alpha=0.5,  # reservado; RRF puro por ahora (D7)
                filters=filtros_with_user,
                limit=k,
            )
        )
        # Si el adapter uso fusion RRF (coleccion con sparse), los scores son de
        # rank-fusion (~0-0.5), NO similitud coseno: no son comparables al
        # score_threshold (umbral de similitud) y se descartaria todo. En ese
        # modo confiamos en el ranking + top_k_final del reranker. Si degrado a
        # denso (sin sparse), el score SI es coseno y el umbral aplica.
        # Guarda `is True` para que dobles de test sin metodo sigan en modo denso.
        usa_fusion = getattr(self._corpus_repo, "fusion_enabled", lambda: False)() is True

        # Fan-out N2/N3 (jurisprudencia vinculante, doctrina académica):
        # misma query densa+léxica contra cada colección extra. Sin filtros
        # de expediente (puntos globales, igual que normas de competencia).
        # Se conserva usuario_id (Regla 4).
        # Solo usuario_id (Regla 4): tipo_fuente, abreviatura y los filtros de
        # expediente/obras son del corpus juridico y de las obras; en estas
        # colecciones dejaban cero resultados.
        filtros_extra = {"usuario_id": usuario_id}
        # con_fanout=False: búsqueda acotada (p. ej. completar obras del expediente).
        for repo_extra in self._repos_extra if con_fanout else ():
            _registrar(
                await repo_extra.search_hybrid(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    alpha=0.5,
                    filters=filtros_extra,
                    limit=k,
                )
            )

        # 2) Queries de competencia / dirigidas: filtro de payload + sin umbral.
        if queries_extra:
            dense_extra = await self._embedder.embed([q for q, _ in queries_extra])
            for (q, filtros_payload), dense_q in zip(queries_extra, dense_extra, strict=True):
                # Las normas de competencia son publicas (CPM/CPPM/LOJM): NUNCA
                # filtradas por expediente. Se descarta expediente_id para no
                # contradecir abreviatura=CPM con must(expediente_id=X) (Regla 5
                # aplica a obras, no a normas). Se conserva usuario_id (Regla 4).
                # peso_rrf (opcional) pondera la lista en la fusión; no es un filtro.
                filtros_q = {
                    **{f: v for f, v in filtros_payload.items() if f != "peso_rrf"},
                    "usuario_id": usuario_id,
                }
                # Un artículo exacto es del corpus de normas; un puntero por
                # abreviatura (sentencia o libro fijado) vive en su colección.
                repos_q = (
                    [self._corpus_repo]
                    if "numero_articulo" in filtros_payload
                    else [self._corpus_repo, *self._repos_extra]
                )
                for repo_q in repos_q:
                    puntos = await repo_q.search_hybrid(
                        dense_vector=dense_q,
                        sparse_vector=compute_bm25_sparse(q),
                        alpha=0.5,
                        filters=filtros_q,
                        limit=k,
                    )
                    _registrar(puntos, float(filtros_payload.get("peso_rrf", 1.0)))
                    competencia_ids.update(sp.qdrant_id for sp in puntos)

        if not mejor_score:
            return []

        if usa_fusion and len(listas) > 1:
            mejor_score = self._fusionar_rrf(listas, mejor_score)

        # Ordenar por score descendente.
        scored_ordenados = sorted(mejor_score.items(), key=lambda kv: kv[1], reverse=True)

        # Hidratar fragmentos desde PG (preserva orden de scores).
        fragmentos = await self._fragmento_repo.get_by_qdrant_ids(
            [qid for qid, _ in scored_ordenados]
        )
        by_id = {f.qdrant_point_id: f for f in fragmentos}

        # El fragmento puede estar en Qdrant y no en PG (estado inconsistente): se omite.
        return [
            (by_id[qid], score)
            for qid, score in scored_ordenados
            if qid in by_id
            and (qid in competencia_ids or usa_fusion or score >= cfg.score_threshold)
        ]

    async def _query_de_busqueda(self, query: str, cfg) -> str:
        """Fase 1.5 (bug sala): limpia el ruido de la query SOLO para la búsqueda.

        Saludos, muletillas e imperativos ensucian el embedding denso y desplazan
        fragmentos relevantes (ej. Art. 115 CPE) fuera del top-k final; la query
        original se conserva intacta para el LLM y el contexto. Capa A: los typos
        se corrigen contra el vocabulario del corpus (cacheado por proceso); si su
        carga falla se degrada al dict mínimo. El toggle admin `normalizar_query`
        permite usar la query cruda.
        """
        from src.domain.services.normalizar_query import normalizar_query

        if not cfg.normalizar_query:
            return query
        try:
            vocabulario = await self._fragmento_repo.listar_vocabulario()
        except Exception:
            vocabulario = None
        return normalizar_query(query, vocabulario)

    @staticmethod
    def _fusionar_rrf(
        listas: list[tuple[float, list[str]]], candidatos: dict[str, float]
    ) -> dict[str, float]:
        """RRF entre listas ponderadas.

        Con fusión RRF cada lista trae scores en su propia escala (no comparables
        entre colecciones): ordenar por max() dejaba a la doctrina o a la
        jurisprudencia fuera del top. Se fusionan los RANKINGS: el mejor de cada
        lista compite en igualdad y un punto que aparece en varias (p. ej. un
        artículo pedido por consulta dirigida y hallado por la búsqueda) suma.
        Sin fusión (score coseno) se conserva el score por el umbral.
        """
        fusion = dict.fromkeys(candidatos, 0.0)
        for peso, lista in listas:
            for pos, qid in enumerate(lista, 1):
                fusion[qid] += peso / (_RRF_K + pos)
        return fusion
