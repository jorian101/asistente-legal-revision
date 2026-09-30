"""Use case: GenerarBorrador — orquesta pipeline → plantilla → LLM → persist.

Sprint 6 Fase 3.1. Llena el ultimo eslabon del pipeline RAG: dado el
ContextoExpandido (Sprint 5), resuelve la plantilla (Fase 2.1), genera
la respuesta juridica via LLM streaming (Fase 2.2), persiste el borrador
y actualiza el historial de consulta con la respuesta final.

D11: consulta_historial.respuesta se persistio NULL en Sprint 3; Sprint 6
lo llena post-stream via actualizar_respuesta.

Flujos:
- consulta_simple → solo stream + actualizar_respuesta
- auto_vista_* / dictamen_radicatoria_* → stream + persistir borrador/respuesta
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from src.application.consultas.sugerir_argumentacion import (
    BloqueArgumentacion,
    SugerenciaArgumentacion,
    ejecutar_sugerencia,
)
from src.application.services.constructor_mensajes import neutralizar_tokens_plantilla
from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.exceptions import (
    ConsultaSinExpedienteError,
    FaltaCompetenciaError,
    RequisitosIncompletosError,
)
from src.domain.services.analizador_vicios import analizar_vicios
from src.domain.services.evaluador_requisitos import faltantes as faltantes_requisitos
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import (
    ContextoRecuperado,
    TipoRespuesta,
)

# Mapeo de TipoRespuesta → TipoBorrador (Literal del dominio Borrador)
_TIPO_BORRADOR_MAP: dict[str, str] = {
    "auto_vista_consulta": "proyecto_auto_vista_consulta",
    "auto_vista_apelacion_incidental": "proyecto_auto_vista_apelacion",
    "dictamen_radicatoria_consulta": "dictamen_radicatoria",
    "dictamen_radicatoria_apelacion": "dictamen_radicatoria",
}

# Reglas globales de redacción de documentos (auto de vista, dictámenes, relación).
# Alineadas con el criterio del vocal (matriz de autoridad y confianza): no completar
# fojas ausentes, marcar `pendiente` toda cita no localizada, no citar sin fuente.
_REGLAS_REDACCION = "\n".join(
    (
        "[REGLAS DE REDACCIÓN — no forman parte del documento]",
        "- Emite únicamente el texto del documento. Sin comentarios sobre cómo lo "
        "redactas, sin notas al redactor y sin repetir estas reglas ni las "
        "instrucciones de la plantilla.",
        "- Toda cita de norma o sentencia debe corresponder a una norma presente en "
        "lo que recibes: los segmentos numerados [S#] del contexto recuperado, el "
        "criterio del vocal o esta plantilla. Si la norma no está en ninguna de esas "
        "partes, escribe [pendiente: cita no verificada]; nunca la cites de memoria "
        "ni la inventes. No escribas los rótulos [S#] en el documento.",
        "- No completes fojas, fechas, plazos ni cifras que no consten en el "
        "expediente ni en el contexto. Omite el dato en lugar de rellenarlo.",
        "- El material de apoyo (contexto, sugerencia de argumentación, criterio "
        "del vocal) es fuente de consulta: no lo copies como parte del documento.",
        "",
    )
)


def con_reglas_de_redaccion(prompt: str, tipo_respuesta: str) -> str:
    """Antepone las reglas de redacción a los tipos que generan documento."""
    if tipo_respuesta == "consulta_simple":
        return prompt
    return f"{_REGLAS_REDACCION}\n{prompt}"


# Referencias fuertes a tareas de cierre (persistencia + evento) en curso. Al
# abortarse un stream la task ASGI se cancela; si solo await-eamos la
# persistencia en el finally, esa escritura muere con CancelledError y la
# consulta queda 'en_progreso'. Aislamos el cierre en una tarea propia (que el
# cancel del request NO cancela) y la sostenemos aqui hasta que termine para
# que el GC no la borre pendiente.
_PENDING_FINALIZE: set = set()

# Registro acotado de productores de stream por historial_id. Evita
# generar dos veces la misma consulta (reintento/recarga) y pone techo
# a generaciones huérfanas si el cliente se desconecta en serie.
_MAX_PRODUCTORES = 32
_PRODUCTORES: dict[int, tuple[asyncio.Task, asyncio.Queue]] = {}

# P1: intervalo minimo entre escrituras del parcial en consulta_historial.
# Throttled para no convertir cada token en un UPDATE — best-effort, nunca
# bloquea ni rompe el streaming si la escritura falla.
_UMBRAL_PARCIAL_S = 1.5


async def _progreso_terminal(stop: asyncio.Event) -> None:
    """Anima un porcentaje de carga en la terminal hasta que llegue el LLM.

    El stream LLM no expone progreso real (solo tokens), asi que el
    porcentaje es una animacion de espera que sube hasta ~95% y queda
    pendiente hasta el primer token (cuando _marcar_respuesta imprime 100%).
    """
    pct = 0
    while not stop.is_set():
        pct = min(pct + 1, 95)
        print(f"\rLLM cargando respuesta... {pct}%", end="", flush=True)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=0.2)
    print(" " * 30, end="\r", flush=True)


async def _marcar_respuesta(stop: asyncio.Event, task: asyncio.Task) -> None:
    """Marca 100% en la terminal y detiene la animacion de progreso."""
    stop.set()
    task.cancel()
    print("\rLLM cargando respuesta... 100%", flush=True)


def _serializar_contexto(contexto: ContextoExpandido) -> dict:
    """Serializa ContextoExpandido a dict JSONB-compatible para trazabilidad legal.

    FIX R2 (no-mistakes codex round 2): la generación LLM debe persistir
    las fuentes consultadas + expansion metrics para auditoría.
    """
    base: dict = {
        "tipo_respuesta": contexto.tipo_respuesta,
        "expediente_id": contexto.expediente_id,
        "fragmentos_count": len(contexto.fragmentos_con_padres),
        "scores": list(contexto.scores),
        "latencia_ms": contexto.latencia_ms,
        "fragmentos": [
            {
                "id": frag.id,
                "norma_id": frag.norma_id,
                "obra_id": frag.obra_id,
                "expediente_id": frag.expediente_id,
                "qdrant_point_id": frag.qdrant_point_id,
                "texto": frag.texto,
                "padre_ref_key": frag.padre_ref_key,
                "nivel_jerarquico": frag.nivel_jerarquico,
            }
            for frag in contexto.fragmentos_con_padres
        ],
    }
    if contexto.trazabilidad is not None:
        base["expansion"] = {
            "realizada": True,
            "latencia_expansion_ms": contexto.trazabilidad.latencia_expansion_ms,
            "nodos_ascendidos": contexto.trazabilidad.nodos_ascendidos,
            "breadcrumbs_count": contexto.trazabilidad.breadcrumbs_count,
            "fragmentos_originales_count": contexto.trazabilidad.fragmentos_originales_count,
            "fragmentos_expandidos_count": contexto.trazabilidad.fragmentos_expandidos_count,
        }
    return base


def _serializar_bloque(bloque: BloqueArgumentacion) -> dict:
    """Serializa un BloqueArgumentacion a dict JSONB-compatible."""
    return {
        "titulo": bloque.titulo,
        "tipo": bloque.tipo,
        "contenido": bloque.contenido,
        "fojas_referidas": list(bloque.fojas_referidas),
        "normas_citadas": list(bloque.normas_citadas),
        "prioridad": bloque.prioridad,
    }


def _serializar_sugerencia(sug: SugerenciaArgumentacion) -> dict:
    """Serializa SugerenciaArgumentacion a dict JSONB-compatible (Fase 5 G3/G4).

    Se persiste en borrador.contexto_recuperado['sugerencia_argumentacion']
    para trazabilidad legal y para que el LLM la use como input estructurado.
    """
    return {
        "tipo_respuesta": sug.tipo_respuesta,
        "fundamentos_hecho": [_serializar_bloque(b) for b in sug.fundamentos_hecho],
        "fundamentos_derecho": [_serializar_bloque(b) for b in sug.fundamentos_derecho],
        "vicios_sanear": [_serializar_bloque(b) for b in sug.vicios_sanear],
        "alertas_competencia": [_serializar_bloque(b) for b in sug.alertas_competencia],
        "alertas_plazos": [_serializar_bloque(b) for b in sug.alertas_plazos],
        "resumen_ejecutivo": sug.resumen_ejecutivo,
        "total_bloques": sug.total_bloques,
    }


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenerarBorradorInput:
    """Input del use case GenerarBorrador (T2: tipo_forzado para fondo/relación)."""

    consulta: str
    usuario_id: int
    expediente_id: int | None = None
    usuario_nombre: str | None = None
    obra_ids: list[int] | None = None
    chat_id: int | None = None
    tipo_forzado: str | None = None
    corpus_refs: list[str] | None = None


@dataclass(frozen=True, slots=True)
class GenerarBorradorResult:
    """Output: tipo de respuesta + stream de tokens + fuentes.

    El stream NO se consume aqui — el router lo materializa via
    StreamingResponse para entregarselo al frontend token por token.

    El borrador NO se persiste: se genera en el chat y el usuario lo guarda
    explicitamente (POST /borradores). `fuentes` es el contexto serializado
    (fragmentos RAG + sugerencia) que viaja con el stream para el guardado.
    """

    tipo_respuesta: TipoRespuesta
    stream: AsyncIterator[str]
    fuentes: dict
    historial_id: int


class GenerarBorrador:
    """Orquesta pipeline RAG → plantilla → LLM streaming → persistencia.

    Args:
        pipeline_rag: PipelineRAG (fases 1-4, Sprint 5).
        resolvedor: ResolvedorPlantilla (Fase 2.1).
        llm_client: LLMClient (Fase 2.2, streaming).
        borrador_repo: BorradorRepo.
        historial_repo: ConsultaHistorialRepo.
        config_repo: ConfiguracionRAGRepo (lee temperatura).
        llm_model_name: Nombre del modelo LLM (get_settings().llm_model_name)
            — se persiste en consulta_historial.modelo_llm.
        event_bus: Bus de eventos para observabilidad LLM (Sprint 7).
            Si el llm_client soporta set_observability_context, se inyecta
            antes del stream para emitir LLMTokensConsumidos.
    """

    def __init__(
        self,
        pipeline_rag: object,
        resolvedor: object,
        llm_client: object,
        borrador_repo: object,
        historial_repo: object,
        config_repo: object,
        llm_model_name: str,
        event_bus: object | None = None,
        expediente_repo: object | None = None,
        obra_repo: object | None = None,
        memoria_conversacional: object | None = None,
        session_factory: object | None = None,
    ) -> None:
        self._pipeline = pipeline_rag
        self._resolvedor = resolvedor
        self._llm = llm_client
        self._borrador_repo = borrador_repo
        self._historial_repo = historial_repo
        self._config_repo = config_repo
        self._llm_model_name = llm_model_name
        self._event_bus = event_bus
        # Fase 5 (G3/G4): repos opcionales para enriquecer la sugerencia de
        # argumentación con datos de expediente/obras (competencia real).
        # None -> se omite el chequeo de competencia (ResultadoCompetencia.vacio()).
        self._expediente_repo = expediente_repo
        self._obra_repo = obra_repo
        # F3: memoria conversacional (ConstructorMemoriaConversacional).
        # None -> chat sin memoria (backward compat).
        self._memoria = memoria_conversacional
        # F2: factory de sesion para persistir la respuesta FINAL fuera del
        # ciclo de vida del request. El StreamingResponse corre DESPUES de que
        # FastAPI cerro la sesion inyectada; reusar self._historial_repo
        # ahi falla con 'connection is closed' y deja la consulta en
        # 'en_progreso'. Con factory abrimos una sesion nueva en el finally.
        # None -> fallback a self._historial_repo (tests unitarios / compat).
        self._session_factory = session_factory

    async def ejecutar(self, req: GenerarBorradorInput) -> GenerarBorradorResult:
        """Ejecuta el pipeline completo RAG + LLM y devuelve un stream.

        Raises:
            src.domain.exceptions.RequisitosIncompletosError:
                Si faltan obrados obligatorios para generar auto de vista o
                dictamen de radicatoria.
            src.domain.exceptions.PlantillaNoImplementadaError:
                Si el tipo_respuesta no tiene plantilla mapeada.
            src.domain.exceptions.ConsultaSinExpedienteError:
                Si el tipo clasificado requiere expediente y no se proveyo.
            src.domain.exceptions.FaltaCompetenciaError:
                Si el expediente no corresponde a la competencia de la SAC.
        """
        # 0. Guard de completitud (vault taxonomia A) — PRE-INSERT y solo
        #    para tipos borrador. Detalle en _guard_requisitos_borrador +
        #    _guard_fondo_relacion_borrador (T2: 422 guía).
        await self._guard_requisitos_borrador(req)
        await self._guard_fondo_relacion_borrador(req)

        # 0b. Via procesal del expediente para desambiguar el clasificador
        #     (bugfix via: "auto de vista" pedido sobre un expediente de
        #     apelacion incidental debe clasificar via apelacion, no
        #     consulta — el clasificador por texto solo es heuristica).
        #     Fail-open: repo ausente o error -> None (sin desambiguar).
        exp_via = None
        if req.expediente_id is not None and self._expediente_repo is not None:
            try:
                exp_via = await self._expediente_repo.obtener(req.expediente_id)
            except Exception:  # noqa: BLE001 — no bloquear la generacion
                exp_via = None
        tipo_proceso = exp_via.tipo_proceso if exp_via is not None else None

        # 1. Persistir consulta_historial ANTES del pipeline para obtener un
        #    historial_id estable que sirva como consulta_id de los eventos SSE
        #    (Task A: unificar consulta_id entre eventos en vivo y replay).
        #    Los metadatos (tipo_respuesta, fuentes, latencia) se rellenan tras
        #    el pipeline via actualizar_metadatos.
        historial_inicial = ConsultaHistorial(
            id=None,
            expediente_id=req.expediente_id,
            usuario_id=req.usuario_id,
            pregunta=req.consulta,
            respuesta=None,  # se llena al done del stream
            tipo_respuesta=None,
            fuentes_recuperadas=None,
            latencia_ms=None,
            modelo_llm=None,
            estado="en_progreso",
        )
        historial_persistido = await self._historial_repo.guardar(historial_inicial)
        historial_id = historial_persistido.id

        # 1b. Pipeline RAG completo (Fases 1-4 Sprint 5) — trae tipo_respuesta.
        #     Se pasa consulta_id=historial_id para que los eventos en vivo
        #     usen el mismo id que el replay del historial.
        #
        # Error-tracking (Sala de Control): si CUALQUIER paso entre el INSERT
        # y el stream falla (pipeline, sugerencia, competencia, plantilla,
        # metadatos), la consulta nunca producira respuesta → se marca
        # estado='error' para que la Sala no la muestre 'En progreso' eterno.
        try:
            contexto = await self._pipeline.ejecutar(
                consulta=req.consulta,
                usuario_id=req.usuario_id,
                expediente_id=req.expediente_id,
                usuario_nombre=req.usuario_nombre,
                expandir=True,
                consulta_id=historial_id,
                obra_ids=req.obra_ids,
                tipo_proceso=tipo_proceso,
                tipo_forzado=req.tipo_forzado,
                corpus_refs=req.corpus_refs,
            )
            # Si el pipeline no tenia expansor, contexto es ContextoRecuperado.
            # LLMClient exige ContextoExpandido — upcast lazy.
            if isinstance(contexto, ContextoRecuperado) and not isinstance(
                contexto, ContextoExpandido
            ):
                contexto = ContextoExpandido(
                    fragmentos_con_padres=contexto.fragmentos,
                    scores=contexto.scores,
                    query_original=contexto.query_original,
                    tipo_respuesta=contexto.tipo_respuesta,
                    expediente_id=contexto.expediente_id,
                    breadcrumbs=(),
                    trazabilidad=None,
                    latencia_ms=contexto.latencia_ms,
                )

            tipo_respuesta: TipoRespuesta = contexto.tipo_respuesta

            # Fase 5 (G3/G4): extraer hechos + concordancias + generar sugerencia
            # de argumentación. Se persiste en fuentes['sugerencia_argumentacion']
            # para trazabilidad legal y como input estructurado al LLM.
            sugerencia_dict: dict | None = None
            sug = await ejecutar_sugerencia(
                contexto,
                usuario_id=req.usuario_id,
                expediente_repo=self._expediente_repo,
                obra_repo=self._obra_repo,
            )
            if sug.total_bloques > 0 or sug.fundamentos_hecho or sug.fundamentos_derecho:
                sugerencia_dict = _serializar_sugerencia(sug)

            # G5 gate bloqueante: si el tipo genera borrador (auto_vista_*,
            # dictamen_*) y EvaluadorCompetencia detecta incompetencia de la SAC,
            # NO se genera la resolucion (evita emitir Auto de Vista/Dictamen
            # sobre materia ajena). Las alertas de competencia se construyen con
            # titulo 'Competencia {criterio}: {estado}' solo cuando estado !=
            # competente (ver sugerir_argumentacion).
            if _TIPO_BORRADOR_MAP.get(tipo_respuesta) is not None:
                incompetentes = [
                    b for b in sug.alertas_competencia if "incompetente" in b.titulo.lower()
                ]
                if incompetentes:
                    motivos = "; ".join(b.contenido for b in incompetentes)
                    raise FaltaCompetenciaError(
                        f"El expediente no es competencia de la SAC: {motivos}"
                    )

            # 2. Resolver plantilla — puede raise PlantillaNoImplementadaError
            #    (se propaga al router para mapear a 422).
            # FIX R1 (no-mistakes codex round 3): resolvedor.resolver es async;
            #    sin await, .replace() opera sobre la coroutine → 500 en runtime.
            #
            # Fase 3 (G1): pasamos los vicios detectados por AnalizadorVicios
            # sobre los fragmentos del contexto. Si hay vicios, el adapter
            # inyecta el listado en
            # {{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}
            # en vez del placeholder hardcodeado.
            fragmentos_texto: list[tuple[int | None, str]] = [
                (f.id, f.texto) for f in contexto.fragmentos_con_padres
            ]
            # Plan D (D5): pasar el delito del expediente para verificar que el
            # articulo citado corresponda al delito imputado (caso 3352).
            # Reutiliza exp_via (fetch 0b) — sin segunda consulta a BD.
            delito_esperado: str | None = None
            if exp_via is not None:
                delito_esperado = getattr(exp_via, "delito", None) or None
            vicios = analizar_vicios(fragmentos_texto, delito_esperado=delito_esperado)
            prompt = await self._resolvedor.resolver(
                tipo_respuesta,
                req.expediente_id,
                vicios=vicios,
                usuario_id=req.usuario_id,
            )

            prompt = con_reglas_de_redaccion(prompt, tipo_respuesta)

            # 3. Inyectar consulta_usuario (slot final sin resolver; el contexto
            #    expandido lo rellena ConstructorMensajes en el adapter).
            # F3: la memoria conversacional se antepone a la consulta para que
            # quede ANTES de la pregunta en el prompt (orden de lectura natural).
            if req.chat_id is not None and self._memoria is not None:
                memoria_texto = await self._memoria.construir(
                    req.chat_id, req.usuario_id, req.consulta
                )
                if memoria_texto:
                    bloque = (
                        "\n\n[HISTORIAL PREVIO DE ESTE CHAT]\n"
                        f"{neutralizar_tokens_plantilla(memoria_texto)}\n"
                    )
                    prompt = prompt.replace(
                        "{{consulta_usuario}}", bloque + "{{consulta_usuario}}", 1
                    )
            prompt = prompt.replace(
                "{{consulta_usuario}}", neutralizar_tokens_plantilla(req.consulta)
            )

            # P4: inyectar la sugerencia estructurada (hitos con foja verificados)
            # al prompt para que el LLM NO invente fojas. Si la plantilla no tiene
            # el slot, el replace no-op y no rompe nada.
            from src.application.consultas.sugerir_argumentacion import serializar_para_llm

            prompt = prompt.replace(
                "{{sugerencia_argumentacion}}",
                neutralizar_tokens_plantilla(serializar_para_llm(sug)),
            )

            # Plan D (D4): inyectar el criterio del Vocal (obras tipo_documento=
            # criterio) como bloque de instrucciones. Aplica a chat simple Y
            # borradores (ambos pasan por GenerarBorrador). Si el repo no está
            # inyectado o no hay criterios, se deja el slot vacío (no rompe).
            prompt = prompt.replace(
                "{{criterio_vocal}}",
                neutralizar_tokens_plantilla(await self._criterio_vocal_texto()),
            )

            # 4. Actualizar metadatos del historial persistido en el paso 1:
            #    tipo_respuesta, fuentes (trazabilidad) y latencia del pipeline.
            #    (La respuesta y modelo_llm se llenan al done del stream.)
            fuentes = _serializar_contexto(contexto)
            if sugerencia_dict is not None:
                fuentes["sugerencia_argumentacion"] = sugerencia_dict
            # Telemetria de modo (Sala de Control / evaluacion): permite
            # correlacionar calidad con extendido vs pensar. Sin modo
            # conciso en esta rama (todo pasa extendido), extendido=True fijo.
            _soporta = getattr(self._llm, "soporta_razonamiento", None)
            try:
                _piensa = bool(_soporta() if callable(_soporta) else False)
            except Exception:  # noqa: BLE001 — telemetria nunca bloquea
                _piensa = False
            fuentes["modo"] = {"extendido": True, "pensar": _piensa}
            await self._historial_repo.actualizar_metadatos(
                historial_id,
                tipo_respuesta=tipo_respuesta,
                fuentes_recuperadas=fuentes,
                latencia_ms=contexto.latencia_ms,
            )

            # Sprint 7: inyecta contexto de observabilidad al LLM client para
            # que emita LLMTokensConsumidos al cierre del stream. Usa historial_id
            # como consulta_id (identificador de la consulta en la BD).
            if self._event_bus is not None and hasattr(self._llm, "set_observability_context"):
                self._llm.set_observability_context(  # type: ignore[attr-defined]
                    event_bus=self._event_bus,
                    consulta_id=historial_id,
                    usuario_id=req.usuario_id,
                )

            # 5. NO se persiste borrador aqui: el borrador se genera en el chat y
            #    el usuario lo guarda explicitamente (POST /borradores). Solo se
            #    mantiene el gate de expediente para los tipos que requieren
            #    expediente (auto_vista_* / dictamen_*) — validacion sin persistir.
            if _TIPO_BORRADOR_MAP.get(tipo_respuesta) is not None and req.expediente_id is None:
                raise ConsultaSinExpedienteError(
                    f"tipo_respuesta={tipo_respuesta!r} requiere expediente_id"
                )

            # 6. Wrapper del stream — yield tokens, acumula, y al done actualiza
            #    la respuesta en consulta_historial (no persiste borrador).
            cfg = await self._config_repo.get_config()
            stream = self._stream_y_persistir(
                prompt=prompt,
                contexto=contexto,
                temperatura=cfg.temperatura,
                historial_id=historial_id,
                usuario_id=req.usuario_id,
                usuario_nombre=req.usuario_nombre,
                expediente_id=req.expediente_id,
                tipo_respuesta=tipo_respuesta,
            )
            return GenerarBorradorResult(
                tipo_respuesta=tipo_respuesta,
                stream=stream,
                fuentes=fuentes,
                historial_id=historial_id,
            )
        except asyncio.CancelledError:
            # Cancelado ANTES del stream (p.ej. cliente desconectado durante la
            # fase RAG, que tarda decenas de s). marcar_error se desacopla con
            # sesion propia para que sobreviva al cancel y la Sala refleje
            # 'error' en lugar de un 'en_progreso' eterno.
            cierre = asyncio.ensure_future(self._marcar_error(historial_id))
            _PENDING_FINALIZE.add(cierre)
            cierre.add_done_callback(_PENDING_FINALIZE.discard)
            raise
        except Exception:
            with contextlib.suppress(Exception):
                await self._historial_repo.marcar_error(historial_id)
            raise

    async def _guard_requisitos_borrador(self, req: GenerarBorradorInput) -> None:
        """Valida obrados de entrada obligatorios (vault taxonomia A).

        - PRE-INSERT: intento bloqueado no deja fila 'error' en Sala.
        - Solo tipos borrador (dictamen/auto_vista): chat simple sigue.
        - Conteo institucional sin filtro propietario (Regla 5 intacta):
          la existencia de la pieza es metadato, no contenido privado.
        - Errores de validación no bloquean la generación (fail-open).
        """
        if req.expediente_id is None or self._obra_repo is None:
            return
        try:
            from src.application.consultas.clasificar_tipo_respuesta import (
                clasificar_tipo_respuesta,
            )

            tipo_preliminar, _ = clasificar_tipo_respuesta(
                consulta=req.consulta,
                expediente_id=req.expediente_id,
                tipo_forzado=req.tipo_forzado,
            )
            if tipo_preliminar not in _TIPO_BORRADOR_MAP or self._expediente_repo is None:
                return

            exp_guard = await self._expediente_repo.obtener(req.expediente_id)
            if exp_guard is None:
                return

            tipos_guard = None
            if hasattr(self._obra_repo, "tipos_activos_por_expediente"):
                candidatos = await self._obra_repo.tipos_activos_por_expediente(  # type: ignore[attr-defined]
                    req.expediente_id
                )
                if isinstance(candidatos, set):
                    tipos_guard = candidatos
            else:
                obras_guard = await self._obra_repo.listar_por_expediente(  # type: ignore[attr-defined]
                    req.expediente_id, req.usuario_id
                )
                tipos_guard = {o.tipo_documento for o in obras_guard}
            if tipos_guard is None:
                return

            falt = faltantes_requisitos(exp_guard.tipo_proceso, tipos_guard)
            if falt:
                raise RequisitosIncompletosError(falt, exp_guard.tipo_proceso, tipo_preliminar)
        except RequisitosIncompletosError:
            raise
        except Exception:  # noqa: BLE001 — no bloquear por error de validación
            log.warning("No se pudo validar los requisitos del expediente", exc_info=True)

    async def _criterio_vocal_texto(self) -> str:
        """Concatena los criterios activos del Vocal como bloque de instrucciones.

        Plan D (D4): lee las obras `tipo_documento='criterio'` (sembradas por
        seed_criterio_vault.py) y las une en un bloque que se inyecta en el
        slot {{criterio_vocal}}. El LLM lo usa como instrucciones de
        comportamiento y verificación. Si el repo no está inyectado o no hay
        criterios, devuelve cadena vacía (el slot queda sin contenido).
        """
        repo = self._obra_repo
        if repo is None or not hasattr(repo, "listar_criterios"):
            return ""
        try:
            criterios = await repo.listar_criterios()
        except Exception:  # noqa: BLE001 — nunca bloquear la generacion
            return ""
        if not criterios:
            return ""
        # Defensivo: los criterios nuevos se guardan sin frontmatter, pero
        # filas viejas pueden traer YAML del vault; no debe llegar al prompt.
        from src.domain.services.criterio_texto import strip_frontmatter

        partes = ["[CRITERIO DEL VOCAL — instrucciones de comportamiento y verificación]"]
        for c in criterios:
            cuerpo = strip_frontmatter(c.contenido_texto or "")
            if not cuerpo:
                continue
            partes.append(f"### {c.nombre_archivo}")
            partes.append(cuerpo)
        return "\n\n".join(partes)

    async def _marcar_error(self, historial_id: int) -> None:
        """Marca la consulta como 'error', con sesion propia si hay factory.

        Usado al cancelarse ANTES del stream: se invoca como tarea desacoplada
        para que la escritura sobreviva a la cancelacion del request.
        """
        from src.adapters.postgres.repos.consulta_historial_repo import (
            get_consulta_historial_repo,
        )

        try:
            if self._session_factory is None:
                await self._historial_repo.marcar_error(historial_id)
                return
            async with self._session_factory() as session:
                await get_consulta_historial_repo(session).marcar_error(historial_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — best-effort
            pass

    async def _guard_fondo_relacion_borrador(self, req: GenerarBorradorInput) -> None:
        """T2: dictamen_fondo y relacion_obrados requieren obrados mínimos.

        Mismo shape que RequisitosIncompletosError: el frontend muestra
        los trozos faltantes con mensaje guía.
        """
        if req.tipo_forzado not in ("dictamen_fondo", "relacion_obrados"):
            return
        if req.expediente_id is None or self._expediente_repo is None:
            return
        exp_via = await self._expediente_repo.obtener(req.expediente_id)
        if exp_via is None:
            return
        obras_minimas: set[str] = set()
        try:
            if hasattr(self._obra_repo, "tipos_activos_por_expediente"):
                cand = await self._obra_repo.tipos_activos_por_expediente(  # type: ignore[attr-defined]
                    req.expediente_id
                )
                if isinstance(cand, set):
                    obras_minimas = cand
            elif self._obra_repo is not None:
                obras_g = await self._obra_repo.listar_por_expediente(  # type: ignore[attr-defined]
                    req.expediente_id, req.usuario_id
                )
                obras_minimas = {o.tipo_documento for o in obras_g}
        except Exception:  # noqa: BLE001 — no bloquear por fallo de repo
            obras_minimas = set()
        if not obras_minimas:
            raise RequisitosIncompletosError(
                {"sentencia", "memorial_apelacion"},
                exp_via.tipo_proceso,
                req.tipo_forzado,
            )

    async def _persistir_respuesta_final(
        self, historial_id: int, contenido: str, modelo: str
    ) -> None:
        """Persiste la respuesta final con una sesion aislada del request.

        El `StreamingResponse` se consume DESPUES de que FastAPI cerro la
        sesion inyectada por `get_db_session`; reusar `self._historial_repo` ahi
        falla con 'connection is closed' (asyncpg) y deja la consulta en
        'en_progreso' en la Sala. Con `session_factory` abrimos una sesion
        nueva. Sin factory (tests unitarios / compat) usa el repo del request.
        """
        if self._session_factory is None:
            await self._historial_repo.actualizar_respuesta(historial_id, contenido, modelo)
            return
        from src.adapters.postgres.repos.consulta_historial_repo import (
            get_consulta_historial_repo,
        )

        async with self._session_factory() as session:
            await get_consulta_historial_repo(session).actualizar_respuesta(
                historial_id, contenido, modelo
            )

    async def _persistir_respuesta_parcial(self, historial_id: int, contenido: str) -> None:
        """P1: persiste el texto acumulado SIN cerrar la consulta.

        A diferencia de `_persistir_respuesta_final`, deja `estado='en_progreso'`
        (ver `actualizar_respuesta_parcial` del repo) para que otra pestaña/chat
        pueda mostrar "se está generando" con el parcial en vivo mientras sigue
        polleando, en vez de darla por terminada al primer parcial. Best-effort:
        una falla acá nunca debe interrumpir el streaming.
        """
        try:
            if self._session_factory is None:
                await self._historial_repo.actualizar_respuesta_parcial(historial_id, contenido)
                return
            from src.adapters.postgres.repos.consulta_historial_repo import (
                get_consulta_historial_repo,
            )

            async with self._session_factory() as session:
                await get_consulta_historial_repo(session).actualizar_respuesta_parcial(
                    historial_id, contenido
                )
        except Exception:  # noqa: BLE001 — el parcial es best-effort
            log.warning(
                "No se pudo persistir el parcial (historial_id=%s)", historial_id, exc_info=True
            )

    async def _stream_y_persistir(
        self,
        prompt: str,
        contexto: ContextoExpandido,
        temperatura: float,
        historial_id: int,
        usuario_id: int,
        usuario_nombre: str | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
    ) -> AsyncIterator[str]:
        """Yield tokens, acumula, y al done persiste la respuesta en el historial.

        El borrador NO se persiste aca (guardado explicito desde el chat).
        Solo se actualiza consulta_historial.respuesta con el texto final.

        La persistencia corre en un `finally` best-effort: si el cliente se
        desconecta (Starlette cancela el StreamingResponse) o el LLM corta a
        mitad, igual se persiste lo acumulado y la consulta NO queda
        'en_progreso' para siempre en la Sala de Control.

        Mientras el LLM procesa el prompt (aun sin primer token) se anima un
        porcentaje de carga en la terminal del backend; al llegar el primer
        token se muestra 100% y se limpia la linea.
        """
        # Productor desacoplado (buena práctica: acotado + reutilizable).
        # Si el cliente se desconecta solo muere este consumidor; el
        # productor termina la generación y persiste el final.
        queue = self._obtener_cola_productora(
            historial_id=historial_id,
            prompt=prompt,
            contexto=contexto,
            temperatura=temperatura,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            expediente_id=expediente_id,
            tipo_respuesta=tipo_respuesta,
        )
        if queue is None:
            # Registro lleno: mensaje ocupado honesto (también persistido).
            ocupado = (
                "\n\n> ⚠️ El servidor está generando muchas respuestas ahora "
                "mismo. Reintente en unos momentos."
            )
            yield ocupado
            await self._finalizar_consulta(
                historial_id=historial_id,
                contenido=ocupado,
                modelo=self._llm_model_name,
                usuario_id=usuario_id,
                usuario_nombre=usuario_nombre,
                expediente_id=expediente_id,
                tipo_respuesta=tipo_respuesta,
                n_tokens=1,
            )
            return
        # La cancelación se propaga (contrato Starlette); el productor
        # desacoplado sigue hasta el final y persiste lo completado.
        while True:
            chunk = await queue.get()
            if chunk is None:  # centinela de fin del productor
                break
            yield chunk

    def _obtener_cola_productora(
        self,
        *,
        historial_id: int,
        prompt: str,
        contexto: ContextoExpandido,
        temperatura: float,
        usuario_id: int,
        usuario_nombre: str | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
    ) -> asyncio.Queue | None:
        """Devuelve la cola del productor para el historial (reuse o nuevo).

        None si el registro está lleno de productores vivos (el caller
        responde mensaje de ocupado). Limpia terminados al pasar.
        """
        for hid in [h for h, (t, _q) in _PRODUCTORES.items() if t.done()]:
            _PRODUCTORES.pop(hid, None)
        existente = _PRODUCTORES.get(historial_id)
        if existente is not None and not existente[0].done():
            return existente[1]
        if len(_PRODUCTORES) >= _MAX_PRODUCTORES:
            return None
        queue: asyncio.Queue = asyncio.Queue()
        productor = asyncio.ensure_future(
            self._producir_respuesta(
                queue,
                prompt=prompt,
                contexto=contexto,
                temperatura=temperatura,
                historial_id=historial_id,
                usuario_id=usuario_id,
                usuario_nombre=usuario_nombre,
                expediente_id=expediente_id,
                tipo_respuesta=tipo_respuesta,
            )
        )
        _PRODUCTORES[historial_id] = (productor, queue)
        _PENDING_FINALIZE.add(productor)
        productor.add_done_callback(_PENDING_FINALIZE.discard)
        productor.add_done_callback(lambda _t, _h=historial_id: _PRODUCTORES.pop(_h, None))
        return queue

    async def _producir_respuesta(
        self,
        queue: asyncio.Queue,
        *,
        prompt: str,
        contexto: ContextoExpandido,
        temperatura: float,
        historial_id: int,
        usuario_id: int,
        usuario_nombre: str | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
    ) -> None:
        """Consume el LLM completo, encola chunks y persiste el final.

        Corre desacoplado del request: sobrevive a la desconexión del
        cliente y siempre deja la consulta terminada (respuesta o error
        amigable), nunca 'en_progreso' eterno.
        """
        tokens: list[str] = []
        stop = asyncio.Event()
        task = asyncio.create_task(_progreso_terminal(stop))
        # El LLM corto a mitad del stream: la consulta NO es un exito.
        fallo = False
        # P1: throttle del parcial — el primer token dispara persistencia
        # inmediata (para que "en_progreso" ya tenga algo que mostrar) y
        # despues como maximo cada _UMBRAL_PARCIAL_S.
        ultimo_parcial = 0.0
        try:
            async for token in self._llm.generar(prompt, contexto, temperatura):
                if not tokens:
                    await _marcar_respuesta(stop, task)
                tokens.append(token)
                queue.put_nowait(token)
                ahora = time.monotonic()
                if ahora - ultimo_parcial >= _UMBRAL_PARCIAL_S:
                    ultimo_parcial = ahora
                    await self._persistir_respuesta_parcial(historial_id, "".join(tokens))
        except Exception as exc:  # noqa: BLE001 — LLM externo puede fallar 503/429/timeout
            # No propagar como 500: el pipeline RAG ya completó. Mensaje
            # amigable con datos reales para el chat.
            llm_error = str(exc)
            fallo = True
            print(f"[WARN] LLM fallo: {llm_error[:500]}", flush=True)
            n_frag = len(contexto.fragmentos_con_padres)
            fallback = (
                "\n\n> ⚠️ El servicio de generación no está disponible ahora mismo "
                "(ningún proveedor LLM de la cadena respondió). El contexto jurídico "
                f"fue recuperado correctamente ({n_frag} "
                f"{'fragmento' if n_frag == 1 else 'fragmentos'}, tipo {tipo_respuesta}), "
                "pero la redacción no pudo completarse. Reintente en unos momentos o "
                "seleccione otro modelo en Configuración."
            )
            if not tokens:
                await _marcar_respuesta(stop, task)
            tokens.append(fallback)
            for tok in fallback.split(" "):
                queue.put_nowait(tok + " ")
        finally:
            stop.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            contenido_final = "".join(tokens)
            modelo_attr = getattr(self._llm, "model_respuesta", None)
            modelo_real = modelo_attr if isinstance(modelo_attr, str) else self._llm_model_name
            await self._finalizar_consulta(
                historial_id=historial_id,
                contenido=contenido_final,
                modelo=modelo_real,
                usuario_id=usuario_id,
                usuario_nombre=usuario_nombre,
                expediente_id=expediente_id,
                tipo_respuesta=tipo_respuesta,
                n_tokens=len(tokens),
                fallo=fallo,
            )
            queue.put_nowait(None)

    async def _finalizar_consulta(
        self,
        *,
        historial_id: int,
        contenido: str,
        modelo: str,
        usuario_id: int,
        usuario_nombre: str | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
        n_tokens: int,
        fallo: bool = False,
    ) -> None:
        """Persiste la respuesta final y publica GeneracionCompletada.

        `fallo` (el LLM corto) ni el contenido vacio cuentan como exito: la
        consulta queda 'error' aunque se guarde el texto parcial o el aviso del
        proveedor, para que el historial no diga 'completado' cuando no lo esta.

        Corre como tarea desacoplada para sobrevivir a la cancelacion del
        stream. Cada paso es best-effort: atrapa EXCEPTO CancelledError propio
        (si esta tarea se cancela explicitamente, no hay nada mas que hacer).
        """
        exito = not fallo and bool(contenido.strip())
        try:
            if contenido.strip():
                await self._persistir_respuesta_final(historial_id, contenido, modelo)
            if not exito:
                # Se guarda lo que haya (parcial o el aviso) pero el estado no
                # miente: sin exito, la consulta queda en 'error'.
                await self._marcar_error(historial_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — persistencia best-effort
            log.exception("No se pudo persistir la respuesta final (historial_id=%s)", historial_id)
        if self._event_bus is not None:
            from src.application.observability import GeneracionCompletada

            evento = GeneracionCompletada(
                consulta_id=historial_id,
                fase="generando",
                timestamp_ms=int(time.time() * 1000),
                usuario_id=usuario_id,
                usuario_nombre=usuario_nombre or f"Usuario {usuario_id}",
                expediente_id=expediente_id,
                tipo_respuesta=tipo_respuesta,
                resumen_legible=("Generación completada" if exito else "Generación interrumpida"),
                respuesta=contenido,
                tokens=n_tokens,
            )
            try:
                await self._event_bus.publish(evento)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — evento best-effort
                log.exception(
                    "No se pudo publicar GeneracionCompletada (historial_id=%s)", historial_id
                )


__all__ = ["GenerarBorrador", "GenerarBorradorInput", "GenerarBorradorResult"]
