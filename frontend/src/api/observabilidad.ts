// Cliente SSE para observabilidad del pipeline RAG (Sprint 7).
//
// Conecta a /api/admin/pipeline/events y emite eventos parseados.
// Solo admin (require_admin en el backend). El prefijo /api lo enruta el
// proxy de Vite; el Bearer token viene del estado de auth.

import { EventSourcePolyfill } from "event-source-polyfill";

import { api, getAccessToken } from "./auth";

export type FasePipeline =
  "entendiendo" | "buscando" | "reordenando" | "expandiendo" | "generando";

export interface EventoBase {
  tipo: string;
  consulta_id: number;
  fase?: FasePipeline;
  timestamp_ms: number;
  usuario_id: number;
  usuario_nombre: string;
  expediente_id: number | null;
  tipo_respuesta: string | null;
}

export interface FaseIniciada extends EventoBase {
  tipo: "FaseIniciada";
  fase: FasePipeline;
}

export interface FaseCompletada extends EventoBase {
  tipo: "FaseCompletada";
  fase: FasePipeline;
  duracion_ms: number;
  resumen_legible: string;
  metadata: Record<string, unknown>;
}

export interface PipelineCompletado extends EventoBase {
  tipo: "PipelineCompletado";
  fase: "generando";
  latencia_total_ms: number;
  resumen_legible: string;
  fragmentos_count: number;
}

export interface GeneracionCompletada extends EventoBase {
  tipo: "GeneracionCompletada";
  fase: "generando";
  resumen_legible: string;
  respuesta: string;
  tokens?: number | null;
}

export interface PipelineError extends EventoBase {
  tipo: "PipelineError";
  fase: "generando";
  fase_fallida: FasePipeline;
  mensaje_error: string;
}

export type EventoPipeline =
  | FaseIniciada
  | FaseCompletada
  | PipelineCompletado
  | GeneracionCompletada
  | PipelineError;

export interface FiltrosSSE {
  filtro_usuario?: number;
  filtro_expediente?: number;
}

/**
 * Conecta al endpoint SSE y llama al callback por cada evento.
 * Retorna una función de cleanup para cerrar la conexión.
 *
 * Reconexión (Task B): el EventSourcePolyfill reconecta automáticamente tras
 * errores transitorios. Solo se rinde tras INTENTOS_MAX fallos consecutivos
 * (avisa por onError y no vuelve a intentar). Esto evita que un corte
 * momentáneo del backend/proxy mate la Sala de Control en vivo.
 */
export function conectarPipelineEvents(
  onEvento: (evento: EventoPipeline) => void,
  onError?: (error: Error) => void,
  filtros?: FiltrosSSE,
  onOpen?: () => void,
): () => void {
  const params = new URLSearchParams();
  if (filtros?.filtro_usuario != null)
    params.set("filtro_usuario", String(filtros.filtro_usuario));
  if (filtros?.filtro_expediente != null)
    params.set("filtro_expediente", String(filtros.filtro_expediente));

  const url = `/api/admin/pipeline/events${params.toString() ? `?${params}` : ""}`;

  let eventSource: EventSourcePolyfill | null = null;
  let cerrado = false;
  let fallosConsecutivos = 0;
  const INTENTOS_MAX = 5;

  const crear = () => {
    if (cerrado) return;
    // Fase 2 (bug sala vacia): leer el token FRESCO en cada conexion/reconexion.
    // Antes se capturaba una sola vez al montar; tras un refresh del access
    // token, cada reconexion (backoff) enviaba el token vencido -> 401 ->
    // el SSE nunca reconectaba y la sala quedaba vacia hasta recargar.
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
    };
    const token = getAccessToken();
    if (token !== null) {
      headers.Authorization = `Bearer ${token}`;
    }

    const es = new EventSourcePolyfill(url, { headers });
    eventSource = es;

    es.onopen = () => {
      fallosConsecutivos = 0; // conexión OK: reset del contador
      // Fase 2: avisar al caller (SalaControl recarga el historial para
      // recuperar consultas que arrancaron durante el corte).
      onOpen?.();
    };

    es.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        // Mapear tipo de string a tipo de evento
        let evento: EventoPipeline;
        switch (data.tipo) {
          case "FaseIniciada":
            evento = { ...data, tipo: "FaseIniciada" };
            break;
          case "FaseCompletada":
            evento = { ...data, tipo: "FaseCompletada" };
            break;
          case "PipelineCompletado":
            evento = { ...data, tipo: "PipelineCompletado" };
            break;
          case "PipelineError":
            evento = { ...data, tipo: "PipelineError" };
            break;
          case "GeneracionCompletada":
            evento = { ...data, tipo: "GeneracionCompletada" };
            break;
          default:
            return; // Evento desconocido
        }
        onEvento(evento);
      } catch {
        // Ignorar eventos malformados
      }
    };

    es.onerror = () => {
      es.close();
      eventSource = null;
      if (cerrado) return;
      fallosConsecutivos += 1;
      if (fallosConsecutivos >= INTENTOS_MAX) {
        if (onError)
          onError(
            new Error(
              `No se pudo mantener la conexión en vivo tras ${INTENTOS_MAX} intentos. Recargá para reconectar.`,
            ),
          );
        return; // se rinde; no vuelve a intentar
      }
      // Backoff exponencial: 1s, 2s, 4s, 8s…
      const delay = Math.min(1000 * 2 ** (fallosConsecutivos - 1), 30000);
      setTimeout(crear, delay);
    };
  };

  crear();

  // Cleanup function
  return () => {
    cerrado = true;
    eventSource?.close();
    eventSource = null;
  };
}

// ----- Historial persistido (replay) -----

export interface HistorialPipelineItemDTO {
  id: number;
  usuario_id: number;
  usuario_carnet: string;
  usuario_nombre: string;
  expediente_id: number | null;
  pregunta: string;
  respuesta: string | null;
  tipo_respuesta: string | null;
  latencia_ms: number | null;
  modelo_llm: string | null;
  fuentes_recuperadas: Record<string, unknown> | null;
  created_at: string | null;
  estado: string | null;
}

export interface PaginaHistorialPipelineDTO {
  items: HistorialPipelineItemDTO[];
  total: number;
}

export type EstadoHistorial = "en_progreso" | "terminadas" | "error";

export interface ListarHistorialPipelineParams {
  usuario_id?: number;
  expediente_id?: number;
  tipo_respuesta?: string;
  estado?: EstadoHistorial;
  fecha_desde?: string;
  fecha_hasta?: string;
  texto?: string;
  pagina?: number;
  por_pagina?: number;
}

export const listarHistorialPipeline = (
  params: ListarHistorialPipelineParams = {},
): Promise<PaginaHistorialPipelineDTO> =>
  api
    .get<PaginaHistorialPipelineDTO>("/admin/pipeline/historial", {
      params,
    })
    .then((r) => r.data);
