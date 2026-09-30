"""Servicio: PipelineRAG — orquestador de fases 1-4 del pipeline RAG.

Coordina los servicios que producen la salida:
1. ClasificarTipoRespuesta (fase 1: pure domain).
2. HybridSearcher (fase 2: busqueda hibrida RRF + privacidad Regla 4).
3. RerankerService (fase 3: cross-encoder — opcional, degrada si reranker no configurado).
4. ExpansorContexto (fase 4: expansion jerarquica + Regla 6 — Sprint 5).

Output: ContextoRecuperado (fases 1-3) o ContextoExpandido (fases 1-4).

Observabilidad: emite eventos al bus para trazabilidad en vivo (las fases y
eventos se coordinan desde el Sprint 3, T36; el panel SSE de eventos en
vivo se expone en el ciclo de observabilidad).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.application.observability import (
    FaseCompletada,
    FaseIniciada,
    PipelineCompletado,
    PipelineError,
    get_event_bus,
)
from src.application.observability.background import (
    Publicador,
    nuevo_consulta_id,
    publicar_en_segundo_plano,
)
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado, TipoRespuesta

if TYPE_CHECKING:
    from src.application.observability import EventBus
    from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo
    from src.application.ports.expansor_contexto import ExpansorContexto
    from src.application.services.hybrid_searcher import HybridSearcher
    from src.application.services.reranker_service import RerankerService
    from src.domain.entities.fragmento import Fragmento

log = logging.getLogger(__name__)

# El corpus juridico siempre esta: minimo de normas (leyes) en el contexto final.
_MIN_NORMAS_EN_CONTEXTO = 2
# Cupo de jurisprudencia no explícita, como el de doctrina (2): sin él la fusión RRF
# le daba ~41 % del top aun preguntando por el caso (diagnostico-cobertura).
_CUPO_JURISPRUDENCIA = 3
_CHUNKS_JURISPRUDENCIA = frozenset(
    {"fundamento_de_hecho", "fundamento_de_derecho_analisis", "fundamentacion_del_fallo"}
)


class _Emisor:
    """Publica los eventos de observabilidad de UNA ejecucion del pipeline.

    Cada evento sale como tarea en segundo plano (no bloquea el pipeline) y
    `fase_actual` recuerda la ultima fase iniciada para reportar en que fase fallo.
    """

    def __init__(
        self,
        bus: Publicador,
        consulta_id: int,
        usuario_id: int,
        usuario_nombre: str,
        expediente_id: int | None,
    ) -> None:
        self._bus = bus
        self._consulta_id = consulta_id
        self._usuario_id = usuario_id
        self._usuario_nombre = usuario_nombre
        self._expediente_id = expediente_id
        self.fase_actual: str = "desconocida"

    def _base(self, tipo_respuesta: str | None = None) -> dict:
        return {
            "consulta_id": self._consulta_id,
            "timestamp_ms": int(time.perf_counter() * 1000),
            "usuario_id": self._usuario_id,
            "usuario_nombre": self._usuario_nombre,
            "expediente_id": self._expediente_id,
            "tipo_respuesta": tipo_respuesta,
        }

    def iniciada(self, fase: str) -> None:
        self.fase_actual = fase
        publicar_en_segundo_plano(self._bus, FaseIniciada(fase=fase, **self._base()))

    def completada(self, fase: str, t_ini: float, resumen: str, metadata: dict) -> None:
        publicar_en_segundo_plano(
            self._bus,
            FaseCompletada(
                fase=fase,
                duracion_ms=int((time.perf_counter() - t_ini) * 1000),
                resumen_legible=resumen,
                metadata=metadata,
                **self._base(),
            ),
        )

    def pipeline_completado(
        self, tipo_respuesta: str, latencia_ms: int, fragmentos_count: int
    ) -> None:
        publicar_en_segundo_plano(
            self._bus,
            PipelineCompletado(
                fase="generando",
                latencia_total_ms=latencia_ms,
                resumen_legible=f"Pipeline completado — {fragmentos_count} segmentos finales",
                fragmentos_count=fragmentos_count,
                **self._base(tipo_respuesta),
            ),
        )

    def error(self, exc: Exception) -> None:
        publicar_en_segundo_plano(
            self._bus,
            PipelineError(
                fase="generando",
                fase_fallida=self.fase_actual,
                mensaje_error=str(exc),
                **self._base(),
            ),
        )


class PipelineRAG:
    """Orquestador de las fases del pipeline RAG.

    Atributos:
        buscador: HybridSearcher (fase 2).
        reranker_svc: RerankerService (fase 3). Puede degradar si su port
            interno Reranker es None (reranker no configurado en .env).
        config_repo: ConfiguracionRAGRepo (umbrales top_k_*).
        expansor: ExpansorContexto (fase 4 — Sprint 5). None = degrada
            a fases 1-3 (backward compat con Sprint 3).
        event_bus: Bus de eventos para trazabilidad (fases del Sprint 3).
    """

    def __init__(
        self,
        buscador: HybridSearcher,
        reranker_svc: RerankerService,
        config_repo: ConfiguracionRAGRepo,
        expansor: ExpansorContexto | None = None,
        event_bus: EventBus | None = None,
        obra_repo: object | None = None,
        recomendacion_repo: object | None = None,
    ) -> None:
        self._buscador = buscador
        self._reranker_svc = reranker_svc
        self._config = config_repo
        self._expansor = expansor
        self._event_bus = event_bus
        # Opcional: resuelve obras puntero N2/N3 a corpus_refs (Regla 5
        # via obtener_por_ids). None = sin resolución (compat).
        self._obra_repo = obra_repo
        # Opcional: fallback a recomendadas del expediente cuando el chat
        # no fija corpus_refs explícitos. None = sin fallback (compat).
        self._recomendacion_repo = recomendacion_repo

    async def ejecutar(
        self,
        consulta: str,
        usuario_id: int,
        expediente_id: int | None,
        expandir: bool = True,
        usuario_nombre: str | None = None,
        consulta_id: int | None = None,
        obra_ids: list[int] | None = None,
        tipo_proceso: str | None = None,
        corpus_refs: list[str] | None = None,
        tipo_forzado: str | None = None,
    ) -> ContextoRecuperado:
        """Ejecuta las fases 1-3 (o 1-4 si expansor configurado).

        Args:
            consulta: Texto de la consulta del usuario.
            usuario_id: OBLIGATORIO (Regla 4 — sin default).
            expediente_id: ID del expediente (None si consulta_simple).
            expandir: Si True y expansor configurado, ejecuta Fase 4
                (Sprint 5). Default True — backward compat: callers
                Sprint 3 ignoran este flag.
            usuario_nombre: Nombre del usuario para observabilidad (opcional).
                Si no se provee, usa "Usuario {usuario_id}".
            consulta_id: Identificador estable para los eventos de
                observabilidad (Task A). Si el caller lo provee (ej. el
                historial_id persistido en GenerarBorrador), se usa tal cual
                para que los eventos en vivo coincidan con el replay del
                historial. Si es None, se genera un hash interno (backward
                compat).
            obra_ids: Obras seleccionadas en el chat (filtro opcional).
            corpus_refs: Abreviaturas N2/N3 fijadas al caso (punteros):
                recuperación explícita por abreviatura, sin umbral
                (mismo mecanismo que queries de competencia).
            tipo_proceso: Via procesal del expediente (consulta,
                apelacion_incidental, apelacion_restringida). Se pasa al
                clasificador para desambiguar el tipo de respuesta cuando
                el texto no explicita la via (ver clasificar_tipo_respuesta).

        Returns:
            ContextoRecuperado (fases 1-3) o ContextoExpandido (fases 1-4).
            El tipo retornado depende de si el expansor esta configurado
            y expandir=True.
        """

        t0 = time.perf_counter()
        bus = self._event_bus or get_event_bus()
        if consulta_id is None:
            consulta_id = nuevo_consulta_id()
        emisor = _Emisor(
            bus, consulta_id, usuario_id, usuario_nombre or f"Usuario {usuario_id}", expediente_id
        )

        try:
            # Fase 1 — Clasificar tipo de respuesta y armar filtros
            tipo_respuesta, filtros, refs_punteros = await self._fase_entender(
                emisor,
                consulta=consulta,
                usuario_id=usuario_id,
                expediente_id=expediente_id,
                tipo_proceso=tipo_proceso,
                tipo_forzado=tipo_forzado,
                obra_ids=obra_ids,
                corpus_refs=corpus_refs,
            )

            # Carga de umbrales operativos (Sprint 3, decision D3).
            cfg = await self._config.get_config()

            # Fase 2 — Busqueda hibrida con privacidad (Regla 4) + refuerzos.
            candidatos = await self._fase_buscar(
                emisor,
                consulta=consulta,
                usuario_id=usuario_id,
                expediente_id=expediente_id,
                obra_ids=obra_ids,
                tipo_respuesta=tipo_respuesta,
                filtros=filtros,
                refs_punteros=refs_punteros,
                cfg=cfg,
            )

            # Fase 3 — Reranking (cross-encoder).
            rerankeados = await self._fase_reordenar(emisor, consulta, candidatos, cfg)
            rerankeados = self._reservar_normas(rerankeados, candidatos)
            rerankeados = self._diversificar_obras(rerankeados, candidatos)
            rerankeados = await self._anexar_normas_del_criterio(rerankeados)

            latencia_ms = int((time.perf_counter() - t0) * 1000)

            contexto = ContextoRecuperado(
                fragmentos=tuple(frag for frag, _ in rerankeados),
                scores=tuple(score for _, score in rerankeados),
                query_original=consulta,
                tipo_respuesta=tipo_respuesta,
                expediente_id=expediente_id,
                latencia_ms=latencia_ms,
            )

            # Fase 4 — Expansion jerarquica (Sprint 5, condicional).
            if expandir and self._expansor is not None:
                contexto_expandido = await self._fase_expandir(emisor, contexto, usuario_id)
                emisor.pipeline_completado(tipo_respuesta, latencia_ms, len(rerankeados))
                return contexto_expandido

            # G6: si hay expansor pero expandir=False (ej. consulta_simple),
            # resolver breadcrumbs jerarquicos livianos sin expandir el contexto.
            if not expandir and self._expansor is not None:
                contexto = await self._expansor.resolver_breadcrumbs(
                    contexto=contexto,
                    usuario_id=usuario_id,
                )

            # Sin expansor: pipeline completo (fases 1-3)
            emisor.pipeline_completado(tipo_respuesta, latencia_ms, len(rerankeados))
            return contexto

        except Exception as e:
            emisor.error(e)
            raise

    async def _fase_entender(
        self,
        emisor: _Emisor,
        *,
        consulta: str,
        usuario_id: int,
        expediente_id: int | None,
        tipo_proceso: str | None,
        tipo_forzado: str | None,
        obra_ids: list[int] | None,
        corpus_refs: list[str] | None,
    ) -> tuple[TipoRespuesta, dict[str, str], list[str]]:
        """Fase 1: clasifica la consulta y arma filtros y punteros N2/N3.

        Returns:
            (tipo_respuesta, filtros para el buscador, refs_punteros por abreviatura).
        """
        # Lazy import para evitar ciclo y porque clasificar es pure domain.
        from src.application.consultas.clasificar_tipo_respuesta import (
            clasificar_tipo_respuesta,
        )

        t_fase = time.perf_counter()
        emisor.iniciada("entendiendo")
        tipo_respuesta, filtros = clasificar_tipo_respuesta(
            consulta=consulta,
            expediente_id=expediente_id,
            tipo_proceso=tipo_proceso,
            tipo_forzado=tipo_forzado,
        )
        refs_punteros = self._validar_corpus_refs(corpus_refs)
        # Fallback: recomendadas del expediente cuando el chat no fija nada
        # explícito (el vocal recomendó pero no adjuntó en el chat).
        if not refs_punteros and expediente_id is not None:
            refs_punteros.extend(await self._refs_recomendadas(expediente_id))
        # Filtrar por obras seleccionadas en el chat (Regla 5: las obras deben
        # pertenecer al expediente; el filtro Qdrant combina con la privacidad
        # por usuario). None = todas las visibles. Punteros N2/N3 (obra con
        # corpus_ref) no tienen puntos propios: van a recuperación explícita.
        obra_ids_reales = obra_ids
        if obra_ids and self._obra_repo is not None:
            refs_obras, obra_ids_reales = await self._separar_punteros(
                obra_ids, usuario_id, expediente_id
            )
            refs_punteros.extend(refs_obras)
        if obra_ids_reales:
            filtros["obra_ids"] = obra_ids_reales
        # La consulta que nombra una pieza procesal pide esa pieza, no el expediente entero.
        elif (
            not obra_ids
            and tipo_respuesta == "consulta_simple"
            and expediente_id is not None
            and (acotadas := await self._obras_de_la_pieza(consulta, expediente_id, usuario_id))
        ):
            filtros["obra_ids"] = acotadas
        # Teoria (dictamenes-auditor): los ANTECEDENTES de un borrador se
        # redactan SOLO de los obrados del caso. La doctrina global
        # (expediente_id NULL) no compite: sin ella, fragmentos normativos
        # desplazaban a la relacion de obrados y ExtraerHechos perdia las
        # fojas. La norma de competencia entra via queries_competencia.
        if tipo_respuesta != "consulta_simple":
            filtros["solo_expediente"] = True
        emisor.completada(
            "entendiendo",
            t_fase,
            f"Clasificamos la consulta como '{tipo_respuesta}'",
            {"tipo_respuesta": tipo_respuesta, "filtros": str(filtros)},
        )
        return tipo_respuesta, filtros, refs_punteros

    @staticmethod
    def _validar_corpus_refs(corpus_refs: list[str] | None) -> list[str]:
        """T1: refs directas se validan contra el registry (desconocidas se
        ignoran con warning, nunca 500)."""
        refs_validas: list[str] = []
        if corpus_refs:
            from src.domain.services.segmentacion.registro import SegmentadorRegistry

            for ref in corpus_refs:
                try:
                    SegmentadorRegistry.obtener(ref)
                    refs_validas.append(ref)
                except KeyError:
                    print(f"[WARN] corpus_ref desconocido ignorado: {ref}", flush=True)
        return refs_validas

    async def _refs_recomendadas(self, expediente_id: int) -> list[str]:
        """corpus_refs de las recomendaciones aprobadas del expediente (best-effort)."""
        if self._recomendacion_repo is None:
            return []
        try:
            recs = await self._recomendacion_repo.listar_por_expediente(  # type: ignore[attr-defined]
                expediente_id
            )
            return [r.corpus_ref for r in recs if r.corpus_ref]
        except Exception:  # noqa: BLE001 — fallback best-effort
            log.warning("No se pudieron cargar las recomendaciones del expediente", exc_info=True)
            return []

    async def _obras_de_la_pieza(
        self, consulta: str, expediente_id: int, usuario_id: int
    ) -> list[int]:
        """Obras visibles del expediente del tipo de pieza que nombra la consulta (ADR-005).

        Vacio si no nombra ninguna o si el expediente no la tiene: entonces el alcance sigue
        siendo el expediente entero. Best-effort.
        """
        from src.domain.services.pieza_procesal import tipos_nombrados

        tipos = tipos_nombrados(consulta)
        listar = getattr(self._obra_repo, "listar_por_expediente", None)
        if not tipos or listar is None:
            return []
        try:
            obras = await listar(expediente_id, usuario_id)
        except Exception:  # noqa: BLE001 — best-effort
            log.warning(
                "No se pudieron listar las obras para el alcance de la pieza", exc_info=True
            )
            return []
        return [o.id for o in obras if o.tipo_documento in tipos and not o.corpus_ref]

    async def _separar_punteros(
        self, obra_ids: list[int], usuario_id: int, expediente_id: int | None
    ) -> tuple[list[str], list[int]]:
        """Separa las obras-puntero (con corpus_ref) de las obras reales.

        Returns:
            (corpus_refs de las obras puntero del expediente, obra_ids reales).
        """
        obras = await self._obra_repo.obtener_por_ids(  # type: ignore[attr-defined,union-attr]
            obra_ids, usuario_id
        )
        refs = [
            o.corpus_ref
            for o in obras.values()
            if o.corpus_ref and o.expediente_id == expediente_id
        ]
        reales = [
            oid
            for oid in obra_ids
            if oid not in obras or not getattr(obras[oid], "corpus_ref", None)
        ]
        return refs, reales

    async def _fase_buscar(
        self,
        emisor: _Emisor,
        *,
        consulta: str,
        usuario_id: int,
        expediente_id: int | None,
        obra_ids: list[int] | None,
        tipo_respuesta: TipoRespuesta,
        filtros: dict[str, str],
        refs_punteros: list[str],
        cfg,
    ) -> list[tuple[Fragmento, float]]:
        """Fase 2: busqueda hibrida con privacidad (Regla 4) y refuerzos de recuperacion."""
        # P3: expandir con queries de competencia de la via procesal para
        # recuperar la norma de competencia que la query del usuario no
        # menciona (G5/G6). Vacio para consulta_simple.
        from src.domain.services.instituciones_juridicas import consultas_dirigidas
        from src.domain.services.queries_competencia import queries_competencia

        # Punteros N2/N3 fijados al caso: recuperación explícita por
        # abreviatura (la selección del vocal/auditor siempre entra,
        # sin umbral; mismo mecanismo que queries de competencia).
        queries_punteros: tuple[tuple[str, dict], ...] = tuple(
            (consulta, {"abreviatura": ref}) for ref in refs_punteros
        )

        t_fase = time.perf_counter()
        emisor.iniciada("buscando")
        # Institución nombrada ("debido proceso") o artículo explícito
        # ("art. 115 de la CPE"): recuperación determinista del artículo.
        queries_comp = (
            *queries_competencia(tipo_respuesta),
            *consultas_dirigidas(consulta),
        )
        candidatos = await self._buscador.buscar(
            query=consulta,
            usuario_id=usuario_id,
            filtros=filtros,
            top_k_denso=cfg.top_k_denso,
            top_k_lexico=cfg.top_k_lexico,
            queries_extra=(
                *queries_comp,
                *queries_punteros,
            ),
        )
        # Refuerzos de recuperación para borradores con expediente: obrados
        # del caso si el vector search los filtró, y normas del corpus como
        # candidatas. Ambos mutan `candidatos` in-place (best-effort).
        # El alcance es automático (sin selector): siempre todas las fuentes.
        await self._aplicar_fallback_obras(
            candidatos, tipo_respuesta, expediente_id, obra_ids, usuario_id
        )
        # El alcance efectivo: la seleccion del usuario o la pieza que nombra la consulta.
        await self._completar_obras_del_expediente(
            candidatos,
            consulta,
            expediente_id,
            filtros.get("obra_ids") or obra_ids,
            filtros,
            usuario_id,
            cfg,
        )
        await self._fusionar_normas_corpus(
            candidatos, consulta, tipo_respuesta, expediente_id, usuario_id, cfg
        )
        # Replanteo libros (condición 3): cupo N3 para no desplazar
        # obrados del caso del top. Explícitos del vocal siempre entran.
        refs_explicitas = {
            f.get("abreviatura")
            for _q, f in (*queries_comp, *queries_punteros)
            if isinstance(f, dict)
        }
        self._aplicar_cupo_doctrina(candidatos, refs_explicitas)
        self._aplicar_cupo_jurisprudencia(candidatos, refs_explicitas)
        # Obtener normas únicas consultadas para resumen legible
        normas = list({frag.norma_id for frag, _ in candidatos if frag.norma_id})
        # Resolver abreviaturas de normas (lazy import para evitar ciclo)
        # Usar el repositorio de norma para obtener abreviaturas
        # (simplificado: usar IDs si no hay repo disponible)
        normas_legibles = [str(n) for n in normas]
        emisor.completada(
            "buscando",
            t_fase,
            f"Buscamos en {len(candidatos)} segmentos de {len(normas)} normas",
            {"fragmentos_encontrados": len(candidatos), "normas_consultadas": normas_legibles},
        )
        return candidatos

    @staticmethod
    def _es_norma_legal(frag: Fragmento) -> bool:
        """Ley del corpus: fragmento de norma con forma de articulo (no sentencia ni libro)."""
        return frag.norma_id is not None and str(frag.tipo_chunk).startswith("articulo")

    @classmethod
    def _reservar_normas(
        cls,
        seleccion: list[tuple[Fragmento, float]],
        candidatos: list[tuple[Fragmento, float]],
        minimo: int = _MIN_NORMAS_EN_CONTEXTO,
    ) -> list[tuple[Fragmento, float]]:
        """El corpus juridico siempre esta: si el top trae menos de `minimo` normas
        y hay candidatas, las mejores entran sustituyendo a los ultimos fragmentos
        que no son normas. El resto conserva su orden."""
        actuales = sum(1 for f, _ in seleccion if cls._es_norma_legal(f))
        faltan = minimo - actuales
        if faltan <= 0:
            return seleccion
        en_seleccion = {f.qdrant_point_id for f, _ in seleccion}
        nuevas = [
            (f, s)
            for f, s in candidatos
            if cls._es_norma_legal(f) and f.qdrant_point_id not in en_seleccion
        ][:faltan]
        if not nuevas:
            return seleccion
        resultado = list(seleccion)
        for nueva in nuevas:
            for idx in range(len(resultado) - 1, -1, -1):
                if not cls._es_norma_legal(resultado[idx][0]):
                    resultado[idx] = nueva
                    break
            else:
                break
        return resultado

    async def _fase_reordenar(
        self,
        emisor: _Emisor,
        consulta: str,
        candidatos: list[tuple[Fragmento, float]],
        cfg,
    ) -> list[tuple[Fragmento, float]]:
        """Fase 3: reranking (cross-encoder) con el resumen de la fase para el evento."""
        t_fase = time.perf_counter()
        emisor.iniciada("reordenando")
        rerankeados = await self._reranker_svc.aplicar(
            query=consulta,
            candidatos=candidatos,
            top_k=cfg.top_k_final,
        )
        # Detectar si hubo fallback en reranker (metadata interna)
        reranker_interno = getattr(self._reranker_svc, "_reranker", None)
        if reranker_interno:
            modelo_reranker = getattr(reranker_interno, "_model", "desconocido")
            fallback_usado = getattr(reranker_interno, "_fallback_usado", False)
        else:
            # Reranker no configurado: usamos RRF híbrido como fallback
            modelo_reranker = "RRF híbrido"
            fallback_usado = True
        emisor.completada(
            "reordenando",
            t_fase,
            f"Reordenamos por relevancia — top {cfg.top_k_final} seleccionados",
            {
                "modelo": modelo_reranker,
                "top_k_final": cfg.top_k_final,
                "fallback": fallback_usado,
            },
        )
        return rerankeados

    async def _fase_expandir(
        self, emisor: _Emisor, contexto: ContextoRecuperado, usuario_id: int
    ):  # -> ContextoExpandido
        """Fase 4: expansion jerarquica (Sprint 5)."""
        t_fase = time.perf_counter()
        emisor.iniciada("expandiendo")
        contexto_expandido = await self._expansor.expandir(  # type: ignore[union-attr]
            contexto=contexto,
            usuario_id=usuario_id,
        )
        if contexto_expandido.trazabilidad:
            nodos = contexto_expandido.trazabilidad.nodos_ascendidos
            breadcrumbs = contexto_expandido.trazabilidad.breadcrumbs_count
        else:
            nodos = 0
            breadcrumbs = 0
        emisor.completada(
            "expandiendo",
            t_fase,
            f"Expandimos con {nodos} nodos padre",
            {
                "nodos_ascendidos": nodos,
                "breadcrumbs_count": breadcrumbs,
            },
        )
        return contexto_expandido

    async def _anexar_normas_del_criterio(
        self, seleccion: list[tuple[Fragmento, float]]
    ) -> list[tuple[Fragmento, float]]:
        """Las normas que cita el criterio del vocal entran como segmentos, fuera del corte.

        El criterio se inyecta al prompt y el modelo cita sus normas; recuperarlas las
        vuelve verificables. Se anexan al final (no desplazan el top) y sin duplicar.
        Best-effort: nunca rompe el pipeline.
        """
        from src.domain.services.instituciones_juridicas import articulos_explicitos

        listar = getattr(self._obra_repo, "listar_criterios", None)
        frag_repo = getattr(self._buscador, "_fragmento_repo", None)
        if listar is None or not hasattr(frag_repo, "get_articulos"):
            return seleccion
        try:
            criterios = await listar()
            pares = articulos_explicitos("\n".join(c.contenido_texto or "" for c in criterios))
            if not pares:
                return seleccion
            fragmentos = await frag_repo.get_articulos(list(pares))  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 — best-effort
            log.warning("No se pudieron recuperar las normas del criterio", exc_info=True)
            return seleccion
        resultado = list(seleccion)
        vistos = {f.qdrant_point_id for f, _ in resultado}
        for frag in fragmentos:
            if frag.qdrant_point_id not in vistos:
                vistos.add(frag.qdrant_point_id)
                resultado.append((frag, 0.0))
        return resultado

    async def _completar_obras_del_expediente(
        self,
        candidatos: list[tuple[Fragmento, float]],
        consulta: str,
        expediente_id: int | None,
        obra_ids: list[int] | None,
        filtros: dict,
        usuario_id: int,
        cfg,
    ) -> None:
        """Obras visibles del expediente sin ningún candidato -> su mejor fragmento.

        Una obra con muchos fragmentos llenaba el pozo y dejaba afuera a las demás
        (exp13: 79 frente a 12). Búsqueda acotada a las obras faltantes, sin fan-out.
        Respeta la selección del usuario (`obra_ids`) y la Regla 5 (listar_por_expediente).
        Best-effort: nunca rompe el pipeline.
        """
        listar = getattr(self._obra_repo, "listar_por_expediente", None)
        if expediente_id is None or listar is None:
            return
        try:
            visibles = [o.id for o in await listar(expediente_id, usuario_id) if not o.corpus_ref]
            presentes = {f.obra_id for f, _ in candidatos}
            faltan = [
                oid
                for oid in visibles
                if oid not in presentes and (not obra_ids or oid in obra_ids)
            ]
            if not faltan:
                return
            base = {k: v for k, v in filtros.items() if k in ("expediente_id", "solo_expediente")}
            extra = await self._buscador.buscar(
                query=consulta,
                usuario_id=usuario_id,
                filtros={**base, "obra_ids": faltan},
                top_k_denso=cfg.top_k_denso,
                top_k_lexico=cfg.top_k_lexico,
                con_fanout=False,
            )
        except Exception:  # noqa: BLE001 — best-effort
            log.warning("No se pudieron completar las obras del expediente", exc_info=True)
            return
        vistas = presentes.copy()
        for frag, score in extra:
            if frag.obra_id is not None and frag.obra_id not in vistas:
                vistas.add(frag.obra_id)
                candidatos.append((frag, score))

    @classmethod
    def _diversificar_obras(
        cls,
        seleccion: list[tuple[Fragmento, float]],
        candidatos: list[tuple[Fragmento, float]],
    ) -> list[tuple[Fragmento, float]]:
        """Cada obra candidata que quedó fuera del corte entra con su mejor fragmento.

        Reemplaza, desde el final, un fragmento de una obra repetida y, si no hay,
        jurisprudencia o doctrina. Nunca normas ni el único fragmento de una obra.
        Techo: la mitad del corte, para que un expediente con muchas obras no se coma
        el contexto.
        """
        resultado = list(seleccion)
        presentes = {f.obra_id for f, _ in resultado if f.obra_id is not None}
        faltantes: list[tuple[Fragmento, float]] = []
        for frag, score in candidatos:
            if frag.obra_id is not None and frag.obra_id not in presentes:
                presentes.add(frag.obra_id)
                faltantes.append((frag, score))
        for nueva in faltantes[: len(resultado) // 2]:
            conteo: dict[int, int] = {}
            for f, _ in resultado:
                if f.obra_id is not None:
                    conteo[f.obra_id] = conteo.get(f.obra_id, 0) + 1
            repetida = [
                i
                for i, (f, _) in enumerate(resultado)
                if f.obra_id is not None and conteo[f.obra_id] > 1
            ]
            otra = [
                i
                for i, (f, _) in enumerate(resultado)
                if f.obra_id is None and not cls._es_norma_legal(f)
            ]
            candidatos_idx = repetida or otra
            if not candidatos_idx:
                break
            resultado[candidatos_idx[-1]] = nueva
        return resultado

    async def _aplicar_fallback_obras(
        self,
        candidatos: list[tuple[Fragmento, float]],
        tipo_respuesta: str,
        expediente_id: int | None,
        obra_ids: list[int] | None,
        usuario_id: int,
    ) -> None:
        """Borrador con expediente y sin obras en candidatos -> traer obrados de PG.

        Los antecedentes deben salir de los obrados del caso aunque el vector
        search los filtre por score bajo (OCR ruidoso). Solo cuando el usuario
        NO eligio obras explicitas (`obra_ids`); si eligio un subconjunto se
        respeta y no se inyectan otras. Best-effort: nunca rompe el pipeline.
        """
        if (
            tipo_respuesta == "consulta_simple"
            or expediente_id is None
            or obra_ids
            or any(f.obra_id is not None for f, _ in candidatos)
        ):
            return
        try:
            frag_repo = getattr(self._buscador, "_fragmento_repo", None)
            if frag_repo is None or not hasattr(frag_repo, "get_by_expediente"):
                return
            fallback = await frag_repo.get_by_expediente(  # type: ignore[attr-defined]
                expediente_id, usuario_id, limit=4
            )
            vistos = {f.qdrant_point_id for f, _ in candidatos}
            for frag in fallback:
                if frag.qdrant_point_id not in vistos:
                    candidatos.append((frag, 0.85))
            candidatos.sort(key=lambda x: x[1], reverse=True)
        except Exception:  # noqa: BLE001 — fallback best-effort
            log.warning("No se pudieron traer los obrados del expediente (fallback)", exc_info=True)

    async def _fusionar_normas_corpus(
        self,
        candidatos: list[tuple[Fragmento, float]],
        consulta: str,
        tipo_respuesta: str,
        expediente_id: int | None,
        usuario_id: int,
        cfg,
    ) -> None:
        """Con expediente (consulta o borrador) -> sumar normas del corpus como candidatas.

        Los expedientes citan normas (CPE, CPM, CPPM, LOJM, LOFA, Ley 1970): el
        corpus base siempre se considera (marco-practico RF-05, P5.7). Busqueda
        extra `tipo_fuente=norma` (sin expediente) fusionada al FINAL, sin
        reordenar: si el reranker degrada, los obrados del caso conservan
        prioridad (ExtraerHechos no pierde fojas); con cross-encoder activo
        decide el top entre obras + normas. Best-effort.
        """
        if expediente_id is None:
            return
        try:
            vistas = {f.qdrant_point_id for f, _ in candidatos}
            normas_corpus = await self._buscador.buscar(
                query=consulta,
                usuario_id=usuario_id,
                filtros={"tipo_fuente": "norma"},
                top_k_denso=cfg.top_k_denso,
                top_k_lexico=cfg.top_k_lexico,
                queries_extra=(),
            )
            for frag, score in normas_corpus:
                if frag.qdrant_point_id not in vistas:
                    candidatos.append((frag, score))
                    vistas.add(frag.qdrant_point_id)
        except Exception:  # noqa: BLE001 — fusion de corpus best-effort
            log.warning("No se pudieron sumar las normas del corpus (fusion)", exc_info=True)

    @classmethod
    def _aplicar_cupo_doctrina(
        cls,
        candidatos: list[tuple[Fragmento, float]],
        refs_explicitas: set[str | None],
        cupo: int = 2,
    ) -> None:
        """Cupo N3 (replanteo libros, condición 3): máximo `cupo` chunks de
        doctrina no explícita por respuesta, para no desplazar obrados del
        caso ni jurisprudencia vinculante del top. Los explícitos del vocal
        (por abreviatura) siempre entran. Mutación in-place, orden estable.
        """
        cls._aplicar_cupo(candidatos, refs_explicitas, frozenset({"doctrina_seccion"}), cupo)

    @classmethod
    def _aplicar_cupo_jurisprudencia(
        cls,
        candidatos: list[tuple[Fragmento, float]],
        refs_explicitas: set[str | None],
        cupo: int = _CUPO_JURISPRUDENCIA,
    ) -> None:
        """Igual que el de doctrina, para jurisprudencia no explícita (SCP, Corte IDH)."""
        cls._aplicar_cupo(candidatos, refs_explicitas, _CHUNKS_JURISPRUDENCIA, cupo)

    @staticmethod
    def _aplicar_cupo(
        candidatos: list[tuple[Fragmento, float]],
        refs_explicitas: set[str | None],
        tipos_chunk: frozenset[str],
        cupo: int,
    ) -> None:
        """Máximo `cupo` chunks no explícitos de `tipos_chunk`; in-place, orden estable."""
        vistos = 0
        recortados: list[tuple[Fragmento, float]] = []
        for frag, score in candidatos:
            if frag.tipo_chunk not in tipos_chunk:
                recortados.append((frag, score))
                continue
            clave = frag.padre_ref_key or ""
            explicito = any(ref and clave.startswith(ref) for ref in refs_explicitas)
            if not explicito:
                vistos += 1
                if vistos > cupo:
                    continue
            recortados.append((frag, score))
        candidatos[:] = recortados
