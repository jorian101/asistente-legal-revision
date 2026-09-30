// Cliente HTTP de doctrina (Plan A — flujo de aprobación y doctrina global).
//
// Sigue el patrón de api/expedientes.ts: usa el cliente `api` (baseURL /api,
// Authorization header + retry refresh en 401).
// Endpoints -> rutas de backend/src/routers/doctrina.py.

import { api, getAccessToken } from "./auth";

// ----- DTOs (espejo de response_model de backend/src/routers/doctrina.py) -----

export interface DoctrinaDTO {
  id: number;
  nombre_archivo: string;
  autor?: string | null;
  autor_instancia?: string | null;
  procedencia?: string | null;
  fecha_documento?: string | null;
  estado_visibilidad: string;
  recomendada: boolean;
  motivo_rechazo?: string | null;
  created_at_iso?: string | null;
  corpus?: string | null;
  corpus_ref?: string | null;
}

// ----- GET /doctrina/publica — sidebar derecho del chat -----

export async function listarDoctrinaPrivadaExpediente(
  expedienteId: number,
): Promise<DoctrinaDTO[]> {
  return api
    .get<DoctrinaDTO[]>(
      `/doctrina/expedientes/${expedienteId}/doctrina-privada`,
    )
    .then((r) => r.data);
}

// ----- POST aprobar / rechazar -----

export function descargarObraUrl(obraId: number): string {
  return `${api.defaults.baseURL ?? "/api"}/doctrina/obras/${obraId}/descargar`;
}

export async function descargarObra(obraId: number): Promise<void> {
  const url = descargarObraUrl(obraId);
  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const resp = await fetch(url, {
    method: "GET",
    headers,
    credentials: "include",
  });
  if (!resp.ok) {
    throw new Error(`Error ${resp.status} al descargar el archivo.`);
  }
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  let filename = `obra_${obraId}.pdf`;
  const disposition = resp.headers.get("content-disposition");
  if (disposition && disposition.includes("filename=")) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

// ----- GET /doctrina/events — SSE del supervisor (aprobar/rechazar en vivo) -----

export interface CriterioDTO {
  id: number;
  nombre_archivo: string;
  contenido_texto: string;
  procedencia?: string | null;
  recomendada: boolean;
  updated_at?: string | null;
}

export async function listarCriterios(): Promise<CriterioDTO[]> {
  return api.get<CriterioDTO[]>("/doctrina/criterios").then((r) => r.data);
}

export async function actualizarCriterio(
  obraId: number,
  cambios: {
    contenido_texto?: string;
    procedencia?: string;
    recomendada?: boolean;
  },
): Promise<CriterioDTO> {
  return api
    .patch<CriterioDTO>(`/doctrina/criterios/${obraId}`, cambios)
    .then((r) => r.data);
}

// ----- Plan C: doctrinas propias (privadas + copias de globales) -----

export interface RecomendacionDTO {
  id: number;
  obra_global_id?: number | null;
  nombre_archivo: string;
  expediente_id: number;
  recomendado_por: number;
  recomendado_por_nombre?: string | null;
  recomendado_por_cargo?: string | null;
  estado: string;
  motivo_rechazo?: string | null;
  created_at_iso?: string | null;
  corpus?: string | null;
  corpus_ref?: string | null;
}

export async function listarRecomendadasExpediente(
  expedienteId: number,
): Promise<RecomendacionDTO[]> {
  return api
    .get<RecomendacionDTO[]>(
      `/doctrina/expedientes/${expedienteId}/recomendadas`,
    )
    .then((r) => r.data);
}

export async function listarRecomendacionesPendientes(): Promise<
  RecomendacionDTO[]
> {
  return api
    .get<RecomendacionDTO[]>("/doctrina/recomendaciones/pendientes")
    .then((r) => r.data);
}

export async function aprobarRecomendacion(
  recomendacionId: number,
): Promise<{ recomendacion_id: number; estado: string }> {
  return api
    .post(`/doctrina/recomendaciones/${recomendacionId}/aprobar`)
    .then((r) => r.data);
}

export async function rechazarRecomendacion(
  recomendacionId: number,
  motivo: string,
): Promise<{ recomendacion_id: number; estado: string }> {
  return api
    .post(`/doctrina/recomendaciones/${recomendacionId}/rechazar`, { motivo })
    .then((r) => r.data);
}

export async function aprobarTodasRecomendaciones(
  ids?: number[],
): Promise<{ aprobadas: number }> {
  return api
    .post("/doctrina/recomendaciones/aprobar-todas", ids ?? null)
    .then((r) => r.data);
}
