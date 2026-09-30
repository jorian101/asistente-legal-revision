// Cliente HTTP para gestion de borradores (Sprint 6 — Generacion Respuestas).
//
// Regla 7 Trail of Bits: usuario_id via JWT (no body). Endpoint POST /generar
// devuelve text/plain en streaming token-by-token via ReadableStream.
//
// FIX #2: axios responseType: "stream" no funciona en browser.
// Usamos fetch nativo con response.body (ReadableStream) + TextDecoderStream.

import { api } from "./auth";
import {
  clearAuthState,
  getAccessToken,
  tokenParaReintento,
  reintentaEn401,
} from "./auth";

// ----- DTOs (espejo de backend/src/routers/borradores.py) -----

export type TipoBorrador =
  | "dictamen_radicatoria"
  | "proyecto_auto_vista_consulta"
  | "proyecto_auto_vista_apelacion"
  | "sugerencia_argumentacion";

export type EstadoBorrador =
  "borrador" | "publicado" | "pendiente_oficial" | "oficial";

export interface BorradorBloqueDTO {
  texto: string;
  align: string;
  bold: boolean;
  underline: boolean;
  size_pt: number | null;
  font: string | null;
  heading: number;
}

export interface BorradorDTO {
  id: number;
  expediente_id: number;
  propietario_id: number;
  tipo: TipoBorrador;
  contenido: string;
  estado: EstadoBorrador;
  plantilla_usada: string | null;
  chat_id: number | null;
  mensaje_id: number | null;
  autor_nombre: string | null;
  autor_cargo: string | null;
  created_at: string | null;
  updated_at: string | null;
  layout: BorradorBloqueDTO[] | null;
  razonamiento: string;
}

export interface ContextoExportDTO {
  tamano_hoja: string;
  margenes: { top: number; right: number; bottom: number; left: number };
  font: string;
  size_pt: number;
}

export interface PublicarBorradorResp {
  borrador_id: number;
  estado: EstadoBorrador;
}

export interface GenerarBorradorBody {
  consulta: string;
  expediente_id?: number | null;
}

export interface StreamResultado {
  borradorId: number | null;
  tipoRespuesta: string;
  stream: ReadableStreamDefaultReader<string>;
}

// ----- Helpers: fetch con auth + retry 401 -----

async function fetchWithAuth(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  // Fase 1: getAccessToken() lee el binding vivo; refreshAccessToken es el
  // singleton compartido de auth.ts (evita doble rotacion -> replay -> logout).
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

// ----- Llamadas a API -----

/**
 * POST /borradores/generar — Streaming LLM token por token.
 *
 * Devuelve un ReadableStreamDefaultReader<string> (TextDecoderStream
 * acoplado). El caller hace el loop `while (true) await reader.read()`
 * hasta done. Headers X-Borrador-Id / X-Borrador-Tipo dan contexto.
 */
export async function generarBorrador(
  body: GenerarBorradorBody,
): Promise<StreamResultado> {
  const res = await fetchWithAuth("/api/borradores/generar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status !== 201) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST /borradores/generar status ${res.status}: ${text}`);
  }
  const borradorIdRaw = res.headers.get("X-Borrador-Id") || undefined;
  const borradorId =
    borradorIdRaw && borradorIdRaw !== "" ? Number(borradorIdRaw) : null;
  const tipoRespuesta = res.headers.get("X-Borrador-Tipo") || "";
  const byteStream = res.body as ReadableStream<Uint8Array>;
  const stringStream = byteStream.pipeThrough(
    new TextDecoderStream() as unknown as TransformStream<Uint8Array, string>,
  );
  const stream = stringStream.getReader();
  return { borradorId, tipoRespuesta, stream };
}

export async function publicarBorrador(
  borradorId: number,
): Promise<PublicarBorradorResp> {
  const res = await api.post<PublicarBorradorResp>(
    `/borradores/${borradorId}/publicar`,
  );
  return res.data;
}

export async function listarBorradores(
  expedienteId: number,
): Promise<BorradorDTO[]> {
  const res = await api.get<BorradorDTO[]>("/borradores/", {
    params: { expediente_id: expedienteId },
  });
  return res.data;
}

export async function obtenerBorrador(
  borradorId: number,
): Promise<BorradorDTO> {
  const res = await api.get<BorradorDTO>(`/borradores/${borradorId}`);
  return res.data;
}

export interface GuardarBorradorBody {
  consulta: string;
  expediente_id: number;
  tipo_respuesta: string;
  contenido: string;
  fuentes?: Record<string, unknown> | null;
  chat_id?: number | null;
  mensaje_id?: number | null;
  /** Razonamiento nativo del modelo (modo pensar) a persistir con el borrador. */
  razonamiento?: string;
}

/** POST /borradores — guarda explicitamente un borrador generado en el chat. */
export async function guardarBorrador(
  body: GuardarBorradorBody,
): Promise<BorradorDTO> {
  const res = await api.post<BorradorDTO>("/borradores", body);
  return res.data;
}

/** GET /borradores/mios — lista los borradores del propietario actual. */
export async function listarMisBorradores(): Promise<BorradorDTO[]> {
  const res = await api.get<BorradorDTO[]>("/borradores/mios");
  return res.data;
}

/**
 * GET /borradores/{id}/export — descarga el borrador como .docx.
 *
 * Devuelve el Blob del archivo (Content-Disposition attachment). El
 * caller crea el enlace de descarga (URL.createObjectURL + <a download>).
 */
export async function exportarBorrador(borradorId: number): Promise<Blob> {
  const res = await fetchWithAuth(`/api/borradores/${borradorId}/export`, {
    method: "GET",
  });
  if (res.status !== 200) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `GET /borradores/${borradorId}/export status ${res.status}: ${text}`,
    );
  }
  return res.blob();
}

// ----- Etiquetas de UI (labels amigables) -----

export const TIPO_BORRADOR_LABEL: Record<TipoBorrador, string> = {
  dictamen_radicatoria: "Dictamen de radicatoria",
  proyecto_auto_vista_consulta: "Obrado de vista — consulta",
  proyecto_auto_vista_apelacion: "Obrado de vista — apelación incidental",
  sugerencia_argumentacion: "Sugerencia de argumentación",
};

export async function actualizarBorrador(
  borradorId: number,
  contenido: string,
  layout?: BorradorBloqueDTO[] | null,
): Promise<BorradorDTO> {
  const body: Record<string, unknown> = { contenido };
  if (layout !== undefined) body.layout = layout;
  const res = await api.patch<BorradorDTO>(`/borradores/${borradorId}`, body);
  return res.data;
}

export async function obtenerContextoExport(
  borradorId: number,
): Promise<ContextoExportDTO> {
  const res = await api.get<ContextoExportDTO>(
    `/borradores/${borradorId}/contexto-export`,
  );
  return res.data;
}

// ----- Ciclo obrado -> oficial (Plan) -----

export async function solicitarOficialBorrador(
  borradorId: number,
): Promise<BorradorDTO> {
  const res = await api.post<BorradorDTO>(
    `/borradores/${borradorId}/solicitar-oficial`,
  );
  return res.data;
}

export async function aprobarOficialBorrador(
  borradorId: number,
): Promise<BorradorDTO> {
  const res = await api.post<BorradorDTO>(
    `/borradores/${borradorId}/aprobar-oficial`,
  );
  return res.data;
}

export async function desoficializarBorrador(
  borradorId: number,
  destino: "pendiente_oficial" | "publicado" | "borrador",
): Promise<BorradorDTO> {
  const res = await api.post<BorradorDTO>(
    `/borradores/${borradorId}/desoficializar`,
    { destino },
  );
  return res.data;
}

/** DELETE /borradores/{id} — soft delete (Regla 7: solo propietario). */
export const eliminarBorrador = (borradorId: number): Promise<void> =>
  api.delete(`/borradores/${borradorId}`).then(() => undefined);
