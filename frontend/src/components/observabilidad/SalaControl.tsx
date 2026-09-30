// SalaControl: panel de observabilidad del pipeline RAG (Sprint 7).
//
// Conecta via SSE a /admin/pipeline/events y muestra:
// - Lista de consultas (en vivo + replay filtrado por estado/días/tipo/
//   expediente/usuario) con filtros
// - Modal de selección de usuario (búsqueda por carnet/nombre/rol/cargo)
// - Timeline narrativa de la consulta seleccionada
// - Preview de fragmentos al hacer click en fases
//
// Filtros:
// - Estado: En progreso (default) / Terminadas / Todas. Con "Terminadas" se
//   desactiva el SSE (no se fusionan consultas en vivo a la lista).
// - Días: Hoy / últimos 2/7/30 días / Todo → fecha_desde.
// - Tipo de respuesta y expediente.
// - Usuario: vía modal o por query param `?usuario=<id>` (entrada desde
//   Gestión de Usuarios → "Ver consultas").

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  conectarPipelineEvents,
  listarHistorialPipeline,
  type EstadoHistorial,
  type EventoPipeline,
  type FasePipeline,
} from "../../api/observabilidad";
import { api, type UsuarioDTO } from "../../api/auth";
import { TimelineNarrativa } from "./TimelineNarrativa";
import { FragmentoPreview } from "./FragmentoPreview";
import { toast } from "../../lib/toasts";
import { Button, PageHeader, SeleccionarUsuarioModal } from "../ui";

import "./SalaControl.css";

interface ConsultaActiva {
  id: number;
  usuario_id: number;
  usuario_nombre: string;
  usuario_carnet?: string;
  expediente_id: number | null;
  tipo_respuesta: string | null;
  inicio_ms: number;
  fases: Record<
    FasePipeline,
    {
      estado: "pending" | "running" | "completed" | "error";
      inicio_ms?: number;
      fin_ms?: number;
      resumen?: string;
      metadata?: Record<string, unknown>;
    }
  >;
  ultimo_evento_ms: number;
  fragmentos_count?: number;
  fuentes?: Array<{
    id: number | null;
    norma_id: number | null;
    obra_id: number | null;
    expediente_id: number | null;
    texto: string;
    score?: number;
  }>;
  respuesta?: string | null;
}

interface FuenteRecuperada {
  id?: number | null;
  norma_id?: number | null;
  obra_id?: number | null;
  expediente_id?: number | null;
  texto?: string;
  score?: number;
}

const FASES: FasePipeline[] = [
  "entendiendo",
  "buscando",
  "reordenando",
  "expandiendo",
  "generando",
];

const TIPO_RESPUESTA_LABEL: Record<string, string> = {
  consulta_simple: "Consulta simple",
  auto_vista_consulta: "Auto de vista — consulta",
  auto_vista_apelacion_incidental: "Auto de vista — apelación incidental",
};

const OPCIONES_DIAS: Array<{ value: string; label: string }> = [
  { value: "todo", label: "Todo" },
  { value: "hoy", label: "Hoy" },
  { value: "2", label: "Últimos 2 días" },
  { value: "7", label: "Últimos 7 días" },
  { value: "30", label: "Últimos 30 días" },
];

function faseInicial(): Record<
  FasePipeline,
  {
    estado: "pending" | "running" | "completed" | "error";
    inicio_ms?: number;
    fin_ms?: number;
    resumen?: string;
    metadata?: Record<string, unknown>;
  }
> {
  return {
    entendiendo: { estado: "pending" },
    buscando: { estado: "pending" },
    reordenando: { estado: "pending" },
    expandiendo: { estado: "pending" },
    generando: { estado: "pending" },
  };
}

function fasesCompletadas(): ConsultaActiva["fases"] {
  return {
    entendiendo: { estado: "completed" },
    buscando: { estado: "completed" },
    reordenando: { estado: "completed" },
    expandiendo: { estado: "completed" },
    generando: { estado: "completed" },
  };
}

/** Fases reconstruidas desde el estado persistido del historial (replay).
 *
 * El backend ahora guarda `estado` explicito ('completado' | 'error' |
 * 'en_progreso'): la Sala ya no infiere de NULLs, que dejaban consultas
 * terminadas (pero con respuesta no persistida) 'En progreso' para siempre.
 */
function fasesDesdeEstado(
  estado: string | null | undefined,
): ConsultaActiva["fases"] {
  if (estado === "completado") return fasesCompletadas();
  if (estado === "error") {
    return {
      ...fasesCompletadas(),
      generando: {
        estado: "error",
        resumen: "La respuesta no se completó (error en la generación)",
      },
    };
  }
  return { ...fasesCompletadas(), generando: { estado: "running" } };
}

/** fecha_desde (ISO) según el preset de días; undefined = sin tope. */
function fechaDesdeDias(dias: string): string | undefined {
  if (dias === "todo") return undefined;
  const desde = new Date();
  const diff = dias === "hoy" ? 0 : Number(dias);
  desde.setDate(desde.getDate() - diff);
  desde.setHours(0, 0, 0, 0);
  return desde.toISOString();
}

export function SalaControl(): React.JSX.Element {
  const [consultas, setConsultas] = useState<ConsultaActiva[]>([]);
  const [consultaSeleccionada, setConsultaSeleccionada] = useState<
    number | null
  >(null);
  const [fragmentoPreview, setFragmentoPreview] = useState<
    ConsultaActiva["fases"][FasePipeline] | null
  >(null);

  // Modal de usuario
  const [modalUsuarioAbierto, setModalUsuarioAbierto] = useState(false);
  const [usuarios, setUsuarios] = useState<UsuarioDTO[] | null>(null);

  const cleanupRef = useRef<(() => void) | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  // Filtros
  // Lazy init: ?usuario=<id> (entrada desde Gestión de Usuarios) precarga el
  // filtro sin depender del orden de efectos (evita que el sync de URL borre
  // el param antes de que el preset lo lea).
  const [filtroUsuario, setFiltroUsuario] = useState<number | null>(() => {
    const param = searchParams.get("usuario");
    const id = param !== null ? Number(param) : NaN;
    return Number.isInteger(id) && id > 0 ? id : null;
  });
  const [usuarioSeleccionado, setUsuarioSeleccionado] = useState<{
    id: number;
    nombre: string;
    carnet: string;
  } | null>(null);
  const [filtroExpediente, setFiltroExpediente] = useState("");
  const [filtroEstado, setFiltroEstado] = useState<EstadoHistorial | "todas">(
    "en_progreso",
  );
  const [filtroDias, setFiltroDias] = useState("todo");
  const [filtroTipoRespuesta, setFiltroTipoRespuesta] = useState("");

  // Cargar el catálogo de usuarios (para el modal y resolver ?usuario=).
  useEffect(() => {
    api
      .get<UsuarioDTO[]>("/admin/usuarios")
      .then((r) => setUsuarios(r.data))
      .catch(() => toast("No se pudo cargar la lista de usuarios.", "error"));
  }, []);

  // Mantener la URL sincronizada con el filtro de usuario.
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (filtroUsuario !== null) {
      params.set("usuario", String(filtroUsuario));
    } else {
      params.delete("usuario");
    }
    if (params.toString() !== searchParams.toString()) {
      setSearchParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroUsuario]);

  // Resolver el nombre del usuario filtrado cuando el catálogo carga.
  useEffect(() => {
    if (usuarios === null || filtroUsuario === null) return;
    if (usuarioSeleccionado?.id === filtroUsuario) return;
    const u = usuarios.find((x) => x.id === filtroUsuario);
    if (u)
      setUsuarioSeleccionado({ id: u.id, nombre: u.nombre, carnet: u.carnet });
  }, [usuarios, filtroUsuario, usuarioSeleccionado]);

  // Manejar eventos SSE (no se fusionan en "Terminadas" ni con tipo distinto).
  const handleEvento = useCallback(
    (evento: EventoPipeline) => {
      if (filtroEstado === "terminadas" || filtroEstado === "error") return;
      if (
        filtroTipoRespuesta &&
        evento.tipo_respuesta &&
        evento.tipo_respuesta !== filtroTipoRespuesta
      ) {
        setConsultas((prev) => prev.filter((c) => c.id !== evento.consulta_id));
        return;
      }
      setConsultas((prev) => {
        let consulta = prev.find((c) => c.id === evento.consulta_id);

        if (!consulta) {
          // Nueva consulta
          const nueva: ConsultaActiva = {
            id: evento.consulta_id,
            usuario_id: evento.usuario_id,
            usuario_nombre: evento.usuario_nombre,
            expediente_id: evento.expediente_id,
            tipo_respuesta: evento.tipo_respuesta,
            inicio_ms: evento.timestamp_ms,
            fases: faseInicial(),
            ultimo_evento_ms: evento.timestamp_ms,
          };
          consulta = nueva;
          return [...prev, nueva];
        }

        // Actualizar consulta existente
        const fasesActualizadas = { ...consulta.fases };

        switch (evento.tipo) {
          case "FaseIniciada": {
            const fase = evento.fase!;
            fasesActualizadas[fase] = {
              estado: "running",
              inicio_ms: evento.timestamp_ms,
            };
            break;
          }
          case "FaseCompletada": {
            const fase = evento.fase!;
            fasesActualizadas[fase] = {
              estado: "completed",
              inicio_ms: consulta.fases[fase].inicio_ms,
              fin_ms: evento.timestamp_ms,
              resumen: evento.resumen_legible,
              metadata: evento.metadata,
            };
            break;
          }
          case "PipelineCompletado": {
            // Recuperación lista (fases 1-4 ya completadas): la generación
            // LLM arranca acá. NO se marca 'completado' (eso lo hace
            // GeneracionCompletada al cerrar el stream).
            fasesActualizadas.generando = {
              estado: "running",
              inicio_ms: evento.timestamp_ms,
              resumen: "Recuperación lista — generando respuesta",
            };
            return prev.map((c) =>
              c.id === evento.consulta_id
                ? {
                    ...c,
                    fases: fasesActualizadas,
                    ultimo_evento_ms: evento.timestamp_ms,
                    fragmentos_count: evento.fragmentos_count,
                  }
                : c,
            );
          }
          case "GeneracionCompletada": {
            const generandoPrev = consulta.fases.generando;
            fasesActualizadas.generando = {
              estado: "completed",
              inicio_ms: generandoPrev.inicio_ms ?? evento.timestamp_ms,
              fin_ms: evento.timestamp_ms,
              resumen: evento.resumen_legible,
            };
            break;
          }
          case "PipelineError": {
            const faseFallida = evento.fase_fallida;
            fasesActualizadas[faseFallida] = {
              estado: "error",
              resumen: evento.mensaje_error,
            };
            break;
          }
        }

        return prev.map((c) =>
          c.id === evento.consulta_id
            ? {
                ...c,
                fases: fasesActualizadas,
                ultimo_evento_ms: evento.timestamp_ms,
                ...(evento.tipo === "GeneracionCompletada"
                  ? { respuesta: evento.respuesta }
                  : {}),
              }
            : c,
        );
      });
    },
    [filtroEstado, filtroTipoRespuesta],
  );

  // Cargar ejecuciones pasadas (replay) con TODOS los filtros activos.
  // Antes este método ignoraba los filtros → el historial mezclaba todos los
  // usuarios aunque el SSE estuviera filtrado ("no me deja filtrar").
  const recargarHistorial = useCallback(() => {
    listarHistorialPipeline({
      usuario_id: filtroUsuario ?? undefined,
      expediente_id: filtroExpediente ? Number(filtroExpediente) : undefined,
      tipo_respuesta: filtroTipoRespuesta || undefined,
      estado: filtroEstado === "todas" ? undefined : filtroEstado,
      fecha_desde: fechaDesdeDias(filtroDias),
      pagina: 1,
      por_pagina: 100,
    })
      .then((pagina) => {
        const historico: ConsultaActiva[] = pagina.items.map((h) => {
          const fuentes = h.fuentes_recuperadas as
            | {
                fragmentos_count?: number;
                scores?: number[];
                fragmentos?: FuenteRecuperada[];
              }
            | null
            | undefined;
          const fragmentos: ConsultaActiva["fuentes"] = (
            fuentes?.fragmentos ?? []
          ).map((f, i) => ({
            id: f.id ?? null,
            norma_id: f.norma_id ?? null,
            obra_id: f.obra_id ?? null,
            expediente_id: f.expediente_id ?? null,
            texto: f.texto ?? "",
            score: f.score ?? fuentes?.scores?.[i],
          }));
          const enProgreso = h.respuesta === null || h.tipo_respuesta === null;
          const fases = h.estado
            ? fasesDesdeEstado(h.estado)
            : enProgreso
              ? {
                  ...fasesCompletadas(),
                  generando: { estado: "running" as const },
                }
              : fasesCompletadas();
          return {
            id: h.id,
            usuario_id: h.usuario_id,
            usuario_nombre: h.usuario_nombre,
            usuario_carnet: h.usuario_carnet,
            expediente_id: h.expediente_id,
            tipo_respuesta: h.tipo_respuesta,
            inicio_ms: h.created_at ? Date.parse(h.created_at) : Date.now(),
            fases,
            ultimo_evento_ms: h.created_at
              ? Date.parse(h.created_at)
              : Date.now(),
            fragmentos_count: fuentes?.fragmentos_count ?? fragmentos.length,
            fuentes: fragmentos,
            respuesta: h.respuesta,
          };
        });
        setConsultas((prev) => {
          const vivas = prev.filter(
            (c) => !historico.some((h) => h.id === c.id),
          );
          // En "Terminadas" no hay consultas en vivo: lista pura del historial.
          if (filtroEstado === "terminadas" || filtroEstado === "error")
            return historico;
          return [...historico, ...vivas];
        });
      })
      .catch(() => {
        toast("No se pudo cargar el historial del pipeline.", "error");
      });
  }, [
    filtroUsuario,
    filtroExpediente,
    filtroTipoRespuesta,
    filtroEstado,
    filtroDias,
  ]);

  // Recargar el historial cada vez que cambian los filtros.
  useEffect(() => {
    recargarHistorial();
  }, [recargarHistorial]);

  // Conectar/desconectar SSE. En "Terminadas" no se conecta (solo historial).
  useEffect(() => {
    if (filtroEstado === "terminadas" || filtroEstado === "error") {
      cleanupRef.current?.();
      cleanupRef.current = null;
      return;
    }
    const cleanup = conectarPipelineEvents(
      handleEvento,
      (err) => toast(err.message, "error"),
      {
        filtro_usuario: filtroUsuario || undefined,
        filtro_expediente: filtroExpediente
          ? Number(filtroExpediente)
          : undefined,
      },
      // Fase 2: al reconectar (onopen) se recarga el historial para recuperar
      // consultas que arrancaron mientras el SSE estaba caido (backoff).
      recargarHistorial,
    );
    cleanupRef.current = cleanup;

    return () => {
      cleanup?.();
      cleanupRef.current = null;
    };
  }, [
    handleEvento,
    filtroUsuario,
    filtroExpediente,
    filtroEstado,
    recargarHistorial,
  ]);

  // Auto-seleccionar la consulta más reciente si no hay ninguna seleccionada
  useEffect(() => {
    if (consultas.length > 0 && consultaSeleccionada === null) {
      const masReciente = consultas.reduce((a, b) =>
        a.ultimo_evento_ms > b.ultimo_evento_ms ? a : b,
      );
      setConsultaSeleccionada(masReciente.id);
    }
  }, [consultas, consultaSeleccionada]);

  // Limpiar consultas antiguas (más de 10 min sin actividad) — solo en vivo
  useEffect(() => {
    if (filtroEstado === "terminadas" || filtroEstado === "error") return;
    const interval = setInterval(() => {
      const ahora = Date.now();
      setConsultas((prev) =>
        prev.filter((c) => ahora - c.ultimo_evento_ms < 10 * 60 * 1000),
      );
    }, 60 * 1000);
    return () => clearInterval(interval);
  }, [filtroEstado]);

  const consulta = consultas.find((c) => c.id === consultaSeleccionada);

  const etiquetaUsuario = useMemo(() => {
    if (usuarioSeleccionado) {
      return `${usuarioSeleccionado.nombre} (${usuarioSeleccionado.carnet})`;
    }
    if (filtroUsuario !== null) return `Usuario #${filtroUsuario}`;
    return "Todos los usuarios";
  }, [usuarioSeleccionado, filtroUsuario]);

  // Formatear tiempo relativo
  const formatRelative = (ms: number) => {
    const diff = Date.now() - ms;
    if (diff < 60000) return `${Math.round(diff / 1000)}s`;
    if (diff < 3600000) return `${Math.round(diff / 60000)}m`;
    return `${Math.round(diff / 3600000)}h`;
  };

  const formatTime = (ms: number) => {
    const date = new Date(ms);
    return date.toLocaleTimeString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div className="sala-control">
      <PageHeader
        title="Sala de Control"
        subtitle="Consultas del pipeline RAG en vivo y por estado."
      />

      <div className="sala-control__filters">
        <div className="sala-control__filtro-usuario">
          <span className="sala-control__chip-usuario" title={etiquetaUsuario}>
            {etiquetaUsuario}
            {filtroUsuario !== null && (
              <button
                type="button"
                className="sala-control__chip-clear"
                onClick={() => {
                  setFiltroUsuario(null);
                  setUsuarioSeleccionado(null);
                }}
                aria-label="Quitar filtro de usuario"
              >
                ×
              </button>
            )}
          </span>
          <Button onClick={() => setModalUsuarioAbierto(true)}>
            Seleccionar usuario
          </Button>
        </div>

        <select
          className="select sala-control__filter"
          value={filtroEstado}
          onChange={(e) => {
            setFiltroEstado(e.target.value as EstadoHistorial | "todas");
            setConsultaSeleccionada(null);
          }}
          aria-label="Filtrar por estado"
        >
          <option value="en_progreso">En progreso</option>
          <option value="terminadas">Terminadas</option>
          <option value="error">Con error</option>
          <option value="todas">Todas</option>
        </select>

        <select
          className="select sala-control__filter"
          value={filtroDias}
          onChange={(e) => setFiltroDias(e.target.value)}
          aria-label="Filtrar por días"
        >
          {OPCIONES_DIAS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>

        <select
          className="select sala-control__filter"
          value={filtroTipoRespuesta}
          onChange={(e) => setFiltroTipoRespuesta(e.target.value)}
          aria-label="Filtrar por tipo de consulta"
        >
          <option value="">Todos los tipos</option>
          {Object.entries(TIPO_RESPUESTA_LABEL).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>

        <input
          className="input sala-control__filter sala-control__filter--input"
          value={filtroExpediente}
          onChange={(e) =>
            setFiltroExpediente(e.target.value.replace(/\D/g, ""))
          }
          inputMode="numeric"
          placeholder="Expediente (id)"
          aria-label="Filtrar por expediente"
        />

        <span className="sala-control__status">
          {consultas.length} consulta{consultas.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="sala-control__grid">
        {/* Panel izquierdo: lista de consultas */}
        <aside className="sala-control__sidebar">
          <h2 className="sala-control__sidebar-title">Consultas</h2>
          {consultas.length === 0 ? (
            <p className="sala-control__empty">
              {filtroEstado === "terminadas"
                ? "Sin consultas terminadas con estos filtros."
                : filtroEstado === "error"
                  ? "Sin consultas con error con estos filtros."
                  : "Sin consultas en vivo. Ejecuta una consulta para ver la trazabilidad."}
            </p>
          ) : (
            <ul
              className="sala-control__list"
              role="listbox"
              aria-label="Consultas"
            >
              {consultas
                .slice()
                .sort((a, b) => b.ultimo_evento_ms - a.ultimo_evento_ms)
                .map((c) => {
                  const algunaCorriendo = Object.values(c.fases).some(
                    (f) => f.estado === "running",
                  );
                  const algunaError = Object.values(c.fases).some(
                    (f) => f.estado === "error",
                  );
                  const todasCompletadas = Object.values(c.fases).every(
                    (f) => f.estado === "completed",
                  );

                  let badgeClass = "sala-control__badge--pending";
                  let badgeText = "Pendiente";
                  if (algunaCorriendo) {
                    badgeClass = "sala-control__badge--running";
                    badgeText = "En progreso";
                  } else if (todasCompletadas) {
                    badgeClass = "sala-control__badge--completed";
                    badgeText = "Completado";
                  } else if (algunaError) {
                    badgeClass = "sala-control__badge--error";
                    badgeText = "Error";
                  }

                  return (
                    <li
                      key={c.id}
                      className={`sala-control__item ${consultaSeleccionada === c.id ? "sala-control__item--selected" : ""}`}
                      onClick={() => setConsultaSeleccionada(c.id)}
                      role="option"
                      aria-selected={consultaSeleccionada === c.id}
                    >
                      <div className="sala-control__item-header">
                        <span className="sala-control__item-id">
                          {c.usuario_nombre}
                        </span>
                        <span className={`sala-control__badge ${badgeClass}`}>
                          {badgeText}
                        </span>
                      </div>
                      <div className="sala-control__item-meta">
                        <span>
                          {c.usuario_nombre}
                          {c.usuario_carnet ? ` (${c.usuario_carnet})` : ""}
                        </span>
                        {c.expediente_id && (
                          <span>Expediente #{c.expediente_id}</span>
                        )}
                        {c.tipo_respuesta && (
                          <span>
                            {TIPO_RESPUESTA_LABEL[c.tipo_respuesta] ??
                              c.tipo_respuesta}
                          </span>
                        )}
                      </div>
                      <div className="sala-control__item-time">
                        Iniciada: {formatTime(c.inicio_ms)} · hace{" "}
                        {formatRelative(c.inicio_ms)}
                      </div>
                    </li>
                  );
                })}
            </ul>
          )}
        </aside>

        {/* Panel derecho: timeline + detalle */}
        <main className="sala-control__main">
          {consulta ? (
            <>
              <TimelineNarrativa
                fases={consulta.fases}
                consultaActiva={consulta.id}
                onFaseClick={(fase) => {
                  const faseData = consulta.fases[fase];
                  if (
                    faseData.metadata?.fragmentos_encontrados ||
                    faseData.metadata?.nodos_ascendidos
                  ) {
                    setFragmentoPreview(faseData);
                  }
                }}
              />

              <section
                className="sala-control__detail"
                aria-labelledby="detalle-title"
              >
                <h3 id="detalle-title" className="sala-control__detail-title">
                  Detalle de fases
                </h3>
                <div className="sala-control__phases">
                  {FASES.map((faseKey) => {
                    const fase = consulta.fases[faseKey];
                    const labels: Record<FasePipeline, string> = {
                      entendiendo: "Entendiendo tu pregunta",
                      buscando: "Buscando en el corpus jurídico",
                      reordenando: "Reordenando por relevancia",
                      expandiendo: "Agregando contexto",
                      generando: "Generando respuesta",
                    };

                    let estadoClass = "sala-control__phase--pending";
                    let icon = "⏳";
                    if (fase.estado === "running") {
                      estadoClass = "sala-control__phase--running";
                      icon = "⟳";
                    } else if (fase.estado === "completed") {
                      estadoClass = "sala-control__phase--completed";
                      icon = "✓";
                    } else if (fase.estado === "error") {
                      estadoClass = "sala-control__phase--error";
                      icon = "✕";
                    }

                    return (
                      <article
                        key={faseKey}
                        className={`sala-control__phase ${estadoClass}`}
                        onClick={() => {
                          if (
                            fase.metadata?.fragmentos_encontrados ||
                            fase.metadata?.nodos_ascendidos
                          ) {
                            setFragmentoPreview(fase);
                          }
                        }}
                        style={{
                          cursor:
                            fase.metadata?.fragmentos_encontrados ||
                            fase.metadata?.nodos_ascendidos
                              ? "pointer"
                              : "default",
                        }}
                      >
                        <div className="sala-control__phase-header">
                          <span className="sala-control__phase-icon">
                            {icon}
                          </span>
                          <span className="sala-control__phase-label">
                            {labels[faseKey]}
                          </span>
                          {fase.inicio_ms && fase.fin_ms && (
                            <span className="sala-control__phase-duration">
                              {((fase.fin_ms - fase.inicio_ms) / 1000).toFixed(
                                1,
                              )}
                              s
                            </span>
                          )}
                        </div>
                        {fase.resumen && (
                          <p className="sala-control__phase-resumen">
                            {fase.resumen}
                          </p>
                        )}
                        {fase.estado === "error" && fase.resumen && (
                          <p className="sala-control__phase-error">
                            {fase.resumen}
                          </p>
                        )}
                      </article>
                    );
                  })}
                </div>
              </section>

              {consulta.fuentes && consulta.fuentes.length > 0 && (
                <section
                  className="sala-control__detail"
                  aria-labelledby="fuentes-title"
                >
                  <h3 id="fuentes-title" className="sala-control__detail-title">
                    Fuentes recuperadas
                  </h3>
                  <ul className="sala-control__fuentes">
                    {consulta.fuentes.map((f, i) => (
                      <li key={i} className="sala-control__fuente">
                        <div className="sala-control__fuente-meta">
                          {f.obra_id != null && (
                            <span className="sala-control__badge sala-control__badge--completed">
                              obrado #{f.obra_id}
                            </span>
                          )}
                          {f.norma_id != null && (
                            <span className="sala-control__badge sala-control__badge--completed">
                              norma #{f.norma_id}
                            </span>
                          )}
                          {f.score != null && (
                            <span className="sala-control__fuente-score">
                              {f.score.toFixed(3)}
                            </span>
                          )}
                        </div>
                        <p className="sala-control__fuente-texto">{f.texto}</p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {consulta.respuesta && (
                <section
                  className="sala-control__detail"
                  aria-labelledby="respuesta-title"
                >
                  <h3
                    id="respuesta-title"
                    className="sala-control__detail-title"
                  >
                    Respuesta
                  </h3>
                  <p className="sala-control__respuesta">
                    {consulta.respuesta}
                  </p>
                </section>
              )}
            </>
          ) : (
            <div className="sala-control__empty-state">
              <p>Selecciona una consulta de la lista para ver su timeline.</p>
            </div>
          )}
        </main>
      </div>

      {/* Modal de selección de usuario */}
      <SeleccionarUsuarioModal
        open={modalUsuarioAbierto}
        usuarios={usuarios}
        seleccionado={filtroUsuario ?? undefined}
        onSeleccionar={(u) => {
          setFiltroUsuario(u.id);
          setUsuarioSeleccionado({
            id: u.id,
            nombre: u.nombre,
            carnet: u.carnet,
          });
          setConsultaSeleccionada(null);
          setModalUsuarioAbierto(false);
        }}
        onClose={() => setModalUsuarioAbierto(false)}
      />

      {/* Fragmento Preview Modal */}
      {fragmentoPreview && (
        <FragmentoPreview
          fragmento={{
            id: 0,
            texto: fragmentoPreview.resumen || "Sin detalles disponibles",
            breadcrumb: fragmentoPreview.metadata?.breadcrumb as
              string[] | undefined,
            score: fragmentoPreview.metadata?.score as number | undefined,
            nivel_jerarquico: fragmentoPreview.metadata?.nivel_jerarquico as
              number | undefined,
          }}
          onClose={() => setFragmentoPreview(null)}
        />
      )}
    </div>
  );
}
