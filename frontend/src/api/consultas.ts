// Cliente HTTP para consultas RAG (Sprint 3 — Motor de Recuperación).
//
// Sigue el patrón de api/corpus.ts: usa el cliente `api` (baseURL /api,
// Authorization header + retry refresh en 401 ya configurados en auth.ts).
// Endpoints → rutas de backend/src/routers/consultas.py.
//
// Regla 4 + D4: el backend bloquea admin y toma usuario_id del JWT.
// Aquí no se envía usuario_id: el servidor no lo acepta del cliente.

import {
  api,
  clearAuthState,
  getAccessToken,
  tokenParaReintento,
  reintentaEn401,
} from "./auth";

// DTOs (espejo de los response_model de backend/src/routers/consultas.py)

export type TipoRespuesta =
  "consulta_simple" | "auto_vista_consulta" | "auto_vista_apelacion_incidental";

export interface ConsultaBody {
  consulta: string;
  expediente_id?: number | null;
  /** Obras del expediente a consultar (todas si null/ausente). */
  obra_ids?: number[] | null;
  /** Chat activo: habilita memoria conversacional (F3). */
  chat_id?: number | null;
  /** TipoRespuesta forzado desde Acción rápida (T2). */
  tipo_forzado?: string | null;
  /** Abreviaturas N2/N3 ad-hoc (chips T2, sin puntero). */
  corpus_refs?: string[] | null;
}

export interface FragmentoResultadoDTO {
  id: number | null;
  norma_id: number | null;
  obra_id: number | null;
  expediente_id: number | null;
  qdrant_point_id: string;
  texto: string;
  padre_ref_key: string | null;
  nivel_jerarquico: number | null;
}

export interface ContextoRecuperadoDTO {
  tipo_respuesta: TipoRespuesta;
  expediente_id: number | null;
  fragmentos: FragmentoResultadoDTO[];
  scores: number[];
  latencia_ms: number | null;
  historial_id: number;
}

export const ejecutarConsulta = (
  body: ConsultaBody,
): Promise<ContextoRecuperadoDTO> =>
  api.post<ContextoRecuperadoDTO>("/consultas/", body).then((r) => r.data);

// ----- Streaming LLM (Sprint 6) -----

export interface StreamResultadoConsulta {
  borradorId: number | null;
  tipoRespuesta: string;
  /** Id de consulta_historial: permite traer las citas al terminar el stream. */
  historialId: number | null;
  stream: ReadableStreamDefaultReader<string>;
}

async function fetchWithAuth(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  // Fase 1 (bug kick-al-login): usar getAccessToken() (getter del binding
  // vivo) en vez de desestructurar authState. Desestructurar congelaba una
  // referencia vieja: tras un refresh del axios, el fetch seguia enviando el
  // token vencido -> 401 -> refresh concurrente -> doble rotacion -> logout.
  const headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token !== null) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  headers.set("Accept", "text/plain");

  let response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  // Un unico reintento por llamada (estructural): el segundo fetch no vuelve a entrar.
  if (response.status === 401 && reintentaEn401(url)) {
    try {
      // refreshAccessToken es singleton (auth.ts): si el interceptor de axios
      // ya esta refrescando, este await reutiliza la MISMA promesa -> no hay
      // doble rotacion del refresh token.
      const newToken = await tokenParaReintento(token);
      headers.set("Authorization", `Bearer ${newToken}`);
      response = await fetch(url, {
        ...options,
        headers,
        credentials: "include",
      });
    } catch {
      clearAuthState();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new Error("Unauthorized");
    }
  }
  return response;
}

/**
 * POST /consultas/responder — Streaming LLM token por token.
 *
 * Devuelve un ReadableStreamDefaultReader<string> (TextDecoderStream
 * acoplado). El caller hace el loop `while (true) await reader.read()`
 * hasta done. Headers X-Borrador-Id / X-Borrador-Tipo dan contexto.
 */
export async function responderConsulta(
  body: ConsultaBody,
): Promise<StreamResultadoConsulta> {
  const res = await fetchWithAuth("/api/consultas/responder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status !== 201) {
    const text = await res.text().catch(() => "");
    let detail: unknown = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        detail = (parsed as { detail: unknown }).detail;
      }
    } catch {
      // text no es JSON — se deja como string
    }
    const err = new Error(
      typeof detail === "object" &&
        detail !== null &&
        "message" in (detail as Record<string, unknown>) &&
        typeof (detail as Record<string, unknown>).message === "string"
        ? String((detail as Record<string, unknown>).message)
        : text || `POST /consultas/responder status ${res.status}`,
    ) as Error & { response?: { data?: { detail?: unknown } } };
    err.response = { data: { detail } };
    throw err;
  }
  const borradorIdRaw = res.headers.get("X-Borrador-Id") || undefined;
  const borradorId =
    borradorIdRaw && borradorIdRaw !== "" ? Number(borradorIdRaw) : null;
  const tipoRespuesta = res.headers.get("X-Borrador-Tipo") || "";
  const historialIdRaw = res.headers.get("X-Historial-Id") || undefined;
  const historialId =
    historialIdRaw && historialIdRaw !== "" ? Number(historialIdRaw) : null;
  const byteStream = res.body as ReadableStream<Uint8Array>;
  const stringStream = byteStream.pipeThrough(
    new TextDecoderStream() as unknown as TransformStream<Uint8Array, string>,
  );
  const stream = stringStream.getReader();
  return { borradorId, tipoRespuesta, historialId, stream };
}

// ----- Citas RAG por consulta (fuentes bajo el mensaje del asistente) -----

export interface FragmentoCitaDTO {
  id: number | null;
  norma_id: number | null;
  obra_id: number | null;
  texto: string;
  /** Referencia jerárquica legible (sanitizada en backend, sin refs técnicas). */
  referencia: string | null;
  nivel_jerarquico: number | null;
  /** Enriquecimiento resuelto en backend (etiquetas legibles). */
  norma_nombre?: string | null;
  norma_abreviatura?: string | null;
  obra_tipo?: string | null;
  obra_fecha_documento?: string | null;
  expediente_numero?: string | null;
  categoria?: string | null;
}

export interface FuentesConsultaDTO {
  fragmentos: FragmentoCitaDTO[];
  scores: number[];
}

/** Fuentes RAG de una consulta propia (citas del mensaje del asistente). */
export const obtenerFuentesConsulta = (
  historialId: number,
): Promise<FuentesConsultaDTO> =>
  api
    .get<FuentesConsultaDTO>(`/consultas/historial/${historialId}/fuentes`)
    .then((r) => r.data);

// ----- Detalle de historial (reanudación tras recarga) -----

export interface HistorialDetalleDTO {
  id: number;
  pregunta: string;
  respuesta: string | null;
  estado: string | null;
  tipo_respuesta: string | null;
  modelo_llm: string | null;
}

export const obtenerHistorialDetalle = (
  historialId: number,
): Promise<HistorialDetalleDTO> =>
  api
    .get<HistorialDetalleDTO>(`/consultas/historial/${historialId}`)
    .then((r) => r.data);

// ----- Auditoria admin del historial RAG (Task 8b) -----

export interface HistorialAdminItemDTO {
  id: number;
  expediente_id: number | null;
  usuario_id: number;
  usuario_carnet: string;
  usuario_nombre: string;
  pregunta: string;
  respuesta: string | null;
  tipo_respuesta: string | null;
  latencia_ms: number | null;
  modelo_llm: string | null;
  created_at: string | null;
}

export interface PaginaHistorialAdminDTO {
  items: HistorialAdminItemDTO[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface ListarHistorialAdminParams {
  usuario_id?: number;
  expediente_id?: number;
  tipo_respuesta?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  texto?: string;
  pagina?: number;
  por_pagina?: number;
}

export const listarHistorialAdmin = (
  params: ListarHistorialAdminParams = {},
): Promise<PaginaHistorialAdminDTO> =>
  api
    .get<PaginaHistorialAdminDTO>("/admin/consultas/historial", { params })
    .then((r) => r.data);

export const eliminarHistorialAdmin = (id: number): Promise<void> =>
  api.delete(`/admin/consultas/historial/${id}`).then(() => undefined);

export const eliminarHistorial = (historialId: number): Promise<void> =>
  api.delete(`/consultas/historial/${historialId}`).then(() => undefined);
