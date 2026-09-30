// Cliente del flujo común de fuentes (normas, jurisprudencia y doctrina).
// Endpoints -> backend/src/routers/fuentes.py. Flujo: privada -> pendiente -> global;
// el operador propone y el supervisor aprueba (o rechaza con motivo).

import { api, conProgreso } from "./auth";
import type { RecomendacionDTO } from "./doctrina";
import type { TrabajoEncolado } from "./jobs";

export type CategoriaFuente = "norma" | "jurisprudencia" | "doctrina";
export type EstadoFuente = "privado" | "pendiente" | "global" | "rechazado";
export type JerarquiaNorma = "suprema" | "militar" | "supletoria";

export interface FuenteDTO {
  id: number;
  abreviatura: string;
  nombre: string;
  categoria: CategoriaFuente;
  /** Jurisprudencia: tcp | cidh. */
  subgrupo: string | null;
  estado_visibilidad: EstadoFuente;
  propietario_id: number | null;
  es_propia: boolean;
  motivo_rechazo: string | null;
}

export type { TrabajoEncolado };

export interface PunteroResp {
  obra_id: number;
  estado_visibilidad: string;
}

export interface SubirFuenteParams {
  archivo: File;
  categoria: CategoriaFuente;
  nombre: string;
  /** Norma: suprema | militar | supletoria. */
  jerarquia?: JerarquiaNorma;
  /** Jurisprudencia: scp_tcp | sentencia_cidh. */
  tipo?: "scp_tcp" | "sentencia_cidh";
}

export const listarFuentes = (
  categoria: CategoriaFuente,
): Promise<FuenteDTO[]> =>
  api
    .get<FuenteDTO[]>("/fuentes", { params: { categoria } })
    .then((r) => r.data);

/** Cola de aprobación del supervisor (todas las categorías). */
export const listarFuentesPendientes = (): Promise<FuenteDTO[]> =>
  api.get<FuenteDTO[]>("/fuentes/pendientes").then((r) => r.data);

export const subirFuente = (
  p: SubirFuenteParams,
  onProgreso?: (pct: number) => void,
): Promise<TrabajoEncolado> => {
  const form = new FormData();
  form.append("file", p.archivo);
  form.append("categoria", p.categoria);
  form.append("nombre", p.nombre);
  if (p.jerarquia) form.append("jerarquia", p.jerarquia);
  if (p.tipo) form.append("tipo", p.tipo);
  return api
    .post<TrabajoEncolado>("/fuentes", form, {
      headers: { "Content-Type": "multipart/form-data" },
      ...conProgreso(onProgreso),
    })
    .then((r) => r.data);
};

export const proponerFuente = (id: number): Promise<FuenteDTO> =>
  api.post<FuenteDTO>(`/fuentes/${id}/proponer`).then((r) => r.data);

export const resolverFuente = (
  id: number,
  aprobar: boolean,
  motivo?: string,
): Promise<FuenteDTO> =>
  api
    .post<FuenteDTO>(`/fuentes/${id}/resolver`, { aprobar, motivo })
    .then((r) => r.data);

/** Fija la fuente al caso (o a la consulta si no hay expediente) como puntero. */
export const seleccionarFuente = (
  id: number,
  expedienteId?: number | null,
): Promise<PunteroResp> =>
  api
    .post<PunteroResp>(`/fuentes/${id}/seleccionar`, {
      expediente_id: expedienteId ?? null,
    })
    .then((r) => r.data);

/**
 * Promueve un obrado publicado a norma del corpus (pendiente si es operador).
 * Los checks (obra existe, es propia, publicada) son sincronicos y llegan
 * como error HTTP; el indexado (lento) se encola: 202 con el job_id, que se
 * sigue en /jobs/{job_id}.
 */
export const promoverObraANorma = (
  obraId: number,
  nombre: string,
  jerarquia: JerarquiaNorma,
): Promise<TrabajoEncolado> =>
  api
    .post<TrabajoEncolado>(`/fuentes/desde-obra/${obraId}`, {
      nombre,
      jerarquia,
    })
    .then((r) => r.data);

/** Recomienda una fuente global (por abreviatura) a un expediente. */
export const recomendarFuente = (
  categoria: CategoriaFuente,
  abreviatura: string,
  expedienteId: number,
): Promise<RecomendacionDTO> =>
  api
    .post<RecomendacionDTO>("/doctrina/recomendar", {
      expediente_id: expedienteId,
      corpus: categoria,
      corpus_ref: abreviatura,
    })
    .then((r) => r.data);

export const ESTADO_LABEL: Record<EstadoFuente, string> = {
  privado: "Privada",
  pendiente: "Pendiente de aprobación",
  global: "Global",
  rechazado: "Rechazada",
};

export const CATEGORIA_LABEL: Record<CategoriaFuente, string> = {
  norma: "Normas",
  jurisprudencia: "Jurisprudencia",
  doctrina: "Doctrina",
};

export const SUBGRUPO_LABEL: Record<string, string> = {
  tcp: "Sentencias del TCP",
  cidh: "Sentencias de la Corte IDH",
};

export interface ResolucionTribunalDTO {
  obra_id: number;
  nombre_archivo: string;
  tipo_documento: string;
  expediente_id: number | null;
}

/** Jurisprudencia del propio tribunal: obrados promovidos y autos oficializados. */
export const listarResolucionesTribunal = (): Promise<
  ResolucionTribunalDTO[]
> =>
  api
    .get<ResolucionTribunalDTO[]>("/fuentes/resoluciones-tribunal")
    .then((r) => r.data);
