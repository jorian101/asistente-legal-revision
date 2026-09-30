"""Adapter: ExpansorJerarquicoImpl — expansion jerarquica del contexto (Sprint 5).

Implementa el port ExpansorContexto. Orquesta 5 pasos:
1. Extraer fragmento_ids del ContextoRecuperado.
2. BFS ascendente contra PG (CTE recursivo via FragmentoRepo.get_ascendencia).
3. Batch cargar obras con Regla 5 (ObraRepo.obtener_por_ids).
4. EvaluadorVisibilidad poda fragmentos de obras privadas ajenas (Regla 6).
5. Construir breadcrumbs (path de padre_ref_key desde raiz hasta hijo).

Regla 6 Trail of Bits (BLOQUEANTE): el contexto expandido NUNCA incluye
fragmentos de obras privadas de otros usuarios. EvaluadorVisibilidad los
poda usando el dict de obras filtrado por Regla 5.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.domain.entities.fragmento import Fragmento
from src.domain.services.evaluador_visibilidad import evaluar_visibilidad
from src.domain.services.referencias import etiqueta_legible
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado
from src.domain.value_objects.trazabilidad_pipeline import TrazabilidadPipeline

if TYPE_CHECKING:
    from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo
    from src.application.ports.fragmento_repo import FragmentoRepo
    from src.application.ports.obra_repo import ObraRepo


class ExpansorJerarquicoImpl:
    """Adapter que implementa ExpansorContexto via PG + EvaluadorVisibilidad."""

    def __init__(
        self,
        fragmento_repo: FragmentoRepo,
        obra_repo: ObraRepo,
        config_repo: ConfiguracionRAGRepo,
    ) -> None:
        self._fragmento_repo = fragmento_repo
        self._obra_repo = obra_repo
        self._config_repo = config_repo

    async def expandir(
        self,
        contexto: ContextoRecuperado,
        usuario_id: int,
    ) -> ContextoExpandido:
        """Expande el contexto con padres jerarquicos visibles (Regla 6).

        Args:
            contexto: Output del PipelineRAG (fases 1-3).
            usuario_id: ID del usuario (Regla 4/6 — filtra obrados privados).

        Returns:
            ContextoExpandido con fragmentos_con_padres, breadcrumbs y
            trazabilidad. Ningun fragmento de obra privada ajena.
        """
        cfg = await self._config_repo.get_config()

        # (1) Extraer fragmento_ids del ContextoRecuperado.
        fragmento_ids = [f.id for f in contexto.fragmentos if f.id is not None]

        # (2) BFS ascendente contra PG (Regla 6: padre_ref_id, no padre_ref_key).
        t0 = time.perf_counter()
        padres = await self._fragmento_repo.get_ascendencia(
            fragmento_ids=fragmento_ids,
            max_depth=cfg.max_profundidad_bfs,
        )
        latencia_expansion_ms = int((time.perf_counter() - t0) * 1000)

        # (3) Batch cargar obras con Regla 5 (propias + publicadas).
        obra_ids = {f.obra_id for f in (*contexto.fragmentos, *padres) if f.obra_id is not None}
        obras_por_id = await self._obra_repo.obtener_por_ids(
            obra_ids=list(obra_ids),
            usuario_id=usuario_id,
        )

        # (4) EvaluadorVisibilidad poda fragmentos cuyas obras privadas
        # ajenas no aparecen en obras_por_id (Regla 6).
        hijos_visibles = evaluar_visibilidad(
            fragmentos=list(contexto.fragmentos),
            usuario_id=usuario_id,
            obras_por_id=obras_por_id,
        )
        padres_visibles = evaluar_visibilidad(
            fragmentos=padres,
            usuario_id=usuario_id,
            obras_por_id=obras_por_id,
        )

        # (4.5) Limitar top_k_padres_a_incluir.
        if len(padres_visibles) > cfg.top_k_padres_a_incluir:
            padres_visibles = padres_visibles[: cfg.top_k_padres_a_incluir]

        # (5) Construir breadcrumbs: path de padre_ref_key desde raiz hasta hijo.
        breadcrumbs = self._construir_breadcrumbs(
            hijos=hijos_visibles,
            padres=padres_visibles,
        )

        # Scores: hijos conservan su score del reranker; padres heredan
        # el score maximo del hijo que los alcanzo. Si viene vacio, 0.0.
        # usamos id() (identidad de objeto) en vez de `in` con __eq__:
        # evaluar_visibilidad retorna las mismas instancias (no copias),
        # pero identity-match es immunity a futuras copias defensivas.
        hijos_visibles_ids = {id(f) for f in hijos_visibles}
        scores_hijos = tuple(
            contexto.scores[i]
            for i, frag in enumerate(contexto.fragmentos)
            if id(frag) in hijos_visibles_ids
        )
        scores_padres = self._computar_scores_padres(
            hijos=hijos_visibles,
            padres=padres_visibles,
            scores_hijos=scores_hijos,
        )

        fragmentos_con_padres = tuple(hijos_visibles) + tuple(padres_visibles)
        scores = scores_hijos + scores_padres

        trazabilidad = TrazabilidadPipeline(
            latencia_busqueda_ms=0,
            latencia_reranking_ms=0,
            latencia_expansion_ms=latencia_expansion_ms,
            nodos_ascendidos=len(padres_visibles),
            fragmentos_originales_count=len(contexto.fragmentos),
            fragmentos_expandidos_count=len(fragmentos_con_padres),
            breadcrumbs_count=sum(len(b) for b in breadcrumbs),
            expansion_realizada=True,
        )

        return ContextoExpandido(
            fragmentos_con_padres=fragmentos_con_padres,
            scores=scores,
            query_original=contexto.query_original,
            tipo_respuesta=contexto.tipo_respuesta,
            expediente_id=contexto.expediente_id,
            breadcrumbs=breadcrumbs,
            trazabilidad=trazabilidad,
            latencia_ms=contexto.latencia_ms,
        )

    async def resolver_breadcrumbs(
        self,
        contexto: ContextoRecuperado,
        usuario_id: int,
    ) -> ContextoExpandido:
        """Resuelve breadcrumbs jerarquicos SIN expandir el contexto (G6).

        Reusa get_ascendencia (PG, Regla 6) para validar la jerarquia y
        construye la ruta padre_ref_key de cada fragmento. NO sube los
        padres al contexto: solo la etiqueta de ruta, para que el LLM
        sepa la posicion jerarquica sin pagar tokens de expansion.

        Regla 6: la ruta se resuelve contra PG (padre_ref_id), no se
        confia en padre_ref_key precalculado de Qdrant.
        """
        cfg = await self._config_repo.get_config()

        fragmento_ids = [f.id for f in contexto.fragmentos if f.id is not None]

        t0 = time.perf_counter()
        padres = await self._fragmento_repo.get_ascendencia(
            fragmento_ids=fragmento_ids,
            max_depth=cfg.max_profundidad_bfs,
        )
        latencia_breadcrumbs_ms = int((time.perf_counter() - t0) * 1000)

        # (Regla 6) Podar los ascendidos de obras privadas ajenas antes de
        # usarlos para armar rutas: la ruta no debe reflejar obras que el
        # usuario no puede ver.
        obra_ids = {f.obra_id for f in (*contexto.fragmentos, *padres) if f.obra_id is not None}
        obras_por_id = await self._obra_repo.obtener_por_ids(
            obra_ids=list(obra_ids),
            usuario_id=usuario_id,
        )
        padres_visibles = evaluar_visibilidad(
            fragmentos=padres,
            usuario_id=usuario_id,
            obras_por_id=obras_por_id,
        )

        breadcrumbs = self._construir_breadcrumbs(
            hijos=list(contexto.fragmentos),
            padres=padres_visibles,
        )

        trazabilidad = TrazabilidadPipeline(
            latencia_busqueda_ms=0,
            latencia_reranking_ms=0,
            latencia_expansion_ms=latencia_breadcrumbs_ms,
            nodos_ascendidos=len(padres_visibles),
            fragmentos_originales_count=len(contexto.fragmentos),
            fragmentos_expandidos_count=len(contexto.fragmentos),
            breadcrumbs_count=sum(len(b) for b in breadcrumbs),
            expansion_realizada=False,
        )

        return ContextoExpandido(
            fragmentos_con_padres=contexto.fragmentos,
            scores=contexto.scores,
            query_original=contexto.query_original,
            tipo_respuesta=contexto.tipo_respuesta,
            expediente_id=contexto.expediente_id,
            breadcrumbs=breadcrumbs,
            trazabilidad=trazabilidad,
            latencia_ms=contexto.latencia_ms,
        )

    def _construir_breadcrumbs(
        self,
        hijos: list[Fragmento],
        padres: list[Fragmento],
    ) -> tuple[tuple[str, ...], ...]:
        """Construye un breadcrumb por cada hijo: path raiz -> hijo.

        Usa padre_ref_key como etiqueta de cada nodo, sanitizada via
        etiqueta_legible (sin sufijos tecnicos ni guiones bajos). Los nodos
        sin padre_ref_key se omiten del path: mostrar el qdrant_point_id
        crudo filtraba UUIDs al texto generado. El path va desde
        la raiz (ancestro mas lejano) hasta el hijo.

        Args:
            hijos: Fragmentos hoja visibles.
            padres: Fragmentos padre visibles (ascendidos).

        Returns:
            Tupla de tuplas — una por hijo. Cada tupla es el path legible
            desde raiz hasta el hijo (puede ser vacio si nadie tiene clave).
        """
        # Indexar todos los fragmentos por id para lookup.
        todos: dict[int, Fragmento] = {f.id: f for f in (*hijos, *padres) if f.id is not None}

        breadcrumbs: list[tuple[str, ...]] = []
        for hijo in hijos:
            path: list[str] = []
            actual: Fragmento | None = hijo
            visitados: set[int] = set()

            # Descender desde el hijo hasta la raiz, construir path, luego invertir.
            # Sin padre_ref_key no se aporta etiqueta: omitir el nodo en vez de
            # filtrar un UUID crudo que el LLM termina citando como norma.
            while actual is not None and actual.id is not None:
                if actual.id in visitados:
                    break
                visitados.add(actual.id)
                if actual.padre_ref_key:
                    path.append(etiqueta_legible(actual.padre_ref_key))
                padre_id = actual.padre_ref_id
                actual = todos.get(padre_id) if padre_id is not None else None

            path.reverse()
            breadcrumbs.append(tuple(path))

        return tuple(breadcrumbs)

    def _computar_scores_padres(
        self,
        hijos: list[Fragmento],
        padres: list[Fragmento],
        scores_hijos: tuple[float, ...],
    ) -> tuple[float, ...]:
        """Cada padre hereda el score maximo de los hijos que lo alcanzan.

        Ponytail: sin decay fancy. Si un padre no es alcanzado por ningun
        hijo visible (caso borde donde el hijo fue podado), score 0.0.

        Args:
            hijos: Fragmentos hoja visibles (mismo orden que scores_hijos).
            padres: Fragmentos padre visibles.
            scores_hijos: Scores de los hijos visibles (mismo orden).

        Returns:
            Tupla de scores para los padres, en el mismo orden que `padres`.
        """
        # Map hijo_id -> score para lookup.
        score_por_hijo: dict[int, float] = {}
        for hijo, score in zip(hijos, scores_hijos, strict=True):
            if hijo.id is not None:
                score_por_hijo[hijo.id] = score

        # Para cada padre, buscar el score maximo entre los hijos que lo
        # alcanzan via cadena padre_ref_id. Ponytail: BFS simple desde la
        # raiz hacia abajo usando padre_ref_id como FK.
        todos: dict[int, Fragmento] = {f.id: f for f in (*hijos, *padres) if f.id is not None}

        scores_padres: list[float] = []
        for padre in padres:
            if padre.id is None:
                scores_padres.append(0.0)
                continue

            best_score = 0.0
            # Buscar hijos cuyo ancestro incluye a este padre.
            for hijo in hijos:
                if hijo.id is None:
                    continue
                # Subir desde el hijo hasta encontrar el padre o agotar cadena.
                actual: Fragmento | None = hijo
                visitados: set[int] = set()
                while actual is not None and actual.id is not None:
                    if actual.id in visitados:
                        break
                    visitados.add(actual.id)
                    if actual.id == padre.id:
                        score_hijo = score_por_hijo.get(hijo.id, 0.0)
                        if score_hijo > best_score:
                            best_score = score_hijo
                        break
                    padre_id = actual.padre_ref_id
                    actual = todos.get(padre_id) if padre_id is not None else None

            scores_padres.append(best_score)

        return tuple(scores_padres)
