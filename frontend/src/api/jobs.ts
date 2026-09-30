// Trabajos de indexado: el endpoint de subida responde 202 con un job_id y el
// cliente sigue el estado aca. Endpoints -> backend/src/routers/trabajos.py.
//
// "en_curso" no significa cancelado: al pedir la cancelacion queda
// `cancelacion_solicitada` y el trabajo se detiene en el proximo punto de
// control (terminar una fase puede tardar), asi que hay que seguir polleando.

import { api } from "./auth";

export type EstadoTrabajo = "en_curso" | "completado" | "cancelado" | "error";

/** Respuesta 202 de un endpoint que encola un trabajo (POST /fuentes, POST /admin/corpus/normas). */
export interface TrabajoEncolado {
  job_id: string;
  estado: string;
}

export interface Trabajo {
  id: string;
  tipo: string;
  estado: EstadoTrabajo;
  cancelacion_solicitada: boolean;
  iniciado_en: string;
  terminado_en: string | null;
  error: string | null;
  resultado: Record<string, unknown> | null;
}

export const obtenerTrabajo = (jobId: string): Promise<Trabajo> =>
  api.get<Trabajo>(`/jobs/${jobId}`).then((r) => r.data);

export const cancelarTrabajo = (jobId: string): Promise<Trabajo> =>
  api.post<Trabajo>(`/jobs/${jobId}/cancel`).then((r) => r.data);
