// Cliente HTTP para gestion de expedientes (Sprint 4 — Gestion de Expedientes).
//
// Sigue el patron de api/consultas.ts: usa el cliente `api` (baseURL /api,
// Authorization header + retry refresh en 401 ya configurados en auth.ts).
// Endpoints -> rutas de backend/src/routers/expedientes.py.
//
// Regla 5 (BLOQUEANTE): el backend aplica filtro de visibilidad en el adapter
// (ObraRepoImpl.listar_por_expediente). El cliente solo pasa usuario_id del JWT
// (el server no acepta usuario_id del body — viene del JWT automaticamente).

import { api, conProgreso } from "./auth";

// ----- DTOs (espejo de response_model de backend/src/routers/expedientes.py) -----

export interface AbrirExpedienteBody {
  numero_caso: string;
  tipo_proceso: "consulta" | "apelacion_incidental";
  tribunal_origen: string;
  procesado_nombre: string;
  delito: string;
  procesado_grado?: string | null;
  sentencia_origen?: string | null;
  fojas_total?: number | null;
}

export interface AbrirExpedienteResp {
  expediente_id: number;
  numero_caso: string;
  estado: string;
  creado_at_iso: string;
}

export interface ExpedienteResumen {
  id: number;
  numero_caso: string;
  tipo_proceso: string;
  estado: string;
  tribunal_origen: string;
  procesado_nombre: string;
  delito: string;
  fojas_total: number | null;
  abierto_por: number;
  created_at: string | null;
}

export interface PaginaExpedientes {
  items: ExpedienteResumen[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface ObraCargadaResp {
  obra_id: number;
  estado_visibilidad: string;
  estado_procesamiento: string;
  created_at_iso: string;
}

export interface PublicarObraResp {
  obra_id: number;
  estado_visibilidad: string;
}

export interface ObraResumenDTO {
  id: number;
  expediente_id: number;
  propietario_id: number;
  tipo_documento: string;
  nombre_archivo: string;
  estado_visibilidad: string;
  estado_procesamiento: string;
  es_propia: boolean;
  created_at_iso: string;
  autor_nombre?: string | null;
  autor_cargo?: string | null;
  autor_instancia?: string | null;
  /** Promoción a jurisprudencia: promocion_pendiente | promovida | promocion_rechazada. */
  estado_validacion?: string | null;
}

export interface PromocionResp {
  obra_id: number;
  tipo_documento: string;
  estado_validacion: string | null;
}

export interface PaginaObrasHistorial {
  expediente_id: number;
  obras: ObraResumenDTO[];
  total: number;
}

export interface ListarExpedientesParams {
  pagina?: number;
  por_pagina?: number;
  estado?: "activo" | "archivado";
}

export interface ListarHistorialParams {
  solo_propias?: boolean;
}

// ----- Funciones -----

export const abrirExpediente = (
  body: AbrirExpedienteBody,
): Promise<AbrirExpedienteResp> =>
  api.post<AbrirExpedienteResp>("/expedientes/", body).then((r) => r.data);

export const listarExpedientes = (
  params: ListarExpedientesParams = {},
): Promise<PaginaExpedientes> =>
  api.get<PaginaExpedientes>("/expedientes/", { params }).then((r) => r.data);

// CargarObra usa multipart/form-data con un UploadFile.
export interface CargarObraParams {
  expediente_id: number;
  file: File;
  tipo_documento: string;
  fojas_inicio?: number;
  fojas_fin?: number;
  /** Autor institucional (instancia inferior) si la obra no la subio un usuario. */
  autor_instancia?: string | null;
  onProgreso?: (pct: number) => void;
}

export const cargarObra = ({
  expediente_id,
  file,
  tipo_documento,
  fojas_inicio,
  fojas_fin,
  autor_instancia,
  onProgreso,
}: CargarObraParams): Promise<ObraCargadaResp> => {
  const form = new FormData();
  form.append("file", file);
  form.append("tipo_documento", tipo_documento);
  if (fojas_inicio !== undefined) {
    form.append("fojas_inicio", String(fojas_inicio));
  }
  if (fojas_fin !== undefined) {
    form.append("fojas_fin", String(fojas_fin));
  }
  if (autor_instancia !== undefined && autor_instancia !== null) {
    form.append("autor_instancia", autor_instancia);
  }
  return api
    .post<ObraCargadaResp>(`/expedientes/${expediente_id}/obras`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      ...conProgreso(onProgreso),
    })
    .then((r) => r.data);
};

export const publicarObra = (
  expediente_id: number,
  obra_id: number,
): Promise<PublicarObraResp> =>
  api
    .post<PublicarObraResp>(
      `/expedientes/${expediente_id}/obras/${obra_id}/publicar`,
      {},
    )
    .then((r) => r.data);

/** El propietario propone que su obrado publicado pase a jurisprudencia. */
export const proponerPromocion = (
  expediente_id: number,
  obra_id: number,
): Promise<PromocionResp> =>
  api
    .post<PromocionResp>(
      `/expedientes/${expediente_id}/obras/${obra_id}/proponer-promocion`,
      {},
    )
    .then((r) => r.data);

/** El supervisor aprueba (o promueve directamente) o rechaza con motivo. */
export const resolverPromocion = (
  expediente_id: number,
  obra_id: number,
  aprobar: boolean,
  motivo?: string,
): Promise<PromocionResp> =>
  api
    .post<PromocionResp>(
      `/expedientes/${expediente_id}/obras/${obra_id}/resolver-promocion`,
      { aprobar, motivo },
    )
    .then((r) => r.data);

export const listarHistorialExpediente = (
  expediente_id: number,
  params: ListarHistorialParams = {},
): Promise<PaginaObrasHistorial> =>
  api
    .get<PaginaObrasHistorial>(`/expedientes/${expediente_id}/historial`, {
      params,
    })
    .then((r) => r.data);

export const editarExpediente = (
  expediente_id: number,
  body: Partial<
    Pick<
      AbrirExpedienteBody,
      "numero_caso" | "procesado_nombre" | "delito" | "tribunal_origen"
    >
  >,
): Promise<ExpedienteResumen> => {
  const limpio = Object.fromEntries(
    Object.entries(body).filter(
      ([, v]) => v !== undefined && v !== null && v !== "",
    ),
  );
  return api
    .patch<ExpedienteResumen>(`/expedientes/${expediente_id}`, limpio)
    .then((r) => r.data);
};

export const cambiarEstadoExpediente = (
  expediente_id: number,
  estado: "activo" | "archivado",
): Promise<ExpedienteResumen> =>
  api
    .patch<ExpedienteResumen>(`/expedientes/${expediente_id}/estado`, {
      estado,
    })
    .then((r) => r.data);

export const eliminarObra = (
  expediente_id: number,
  obra_id: number,
): Promise<void> =>
  api
    .delete(`/expedientes/${expediente_id}/obras/${obra_id}`)
    .then(() => undefined);

export interface RequisitosResp {
  tipo_proceso: string;
  requeridos: string[];
  nombres: string[];
}

export const getRequisitos = (tipo_proceso: string): Promise<RequisitosResp> =>
  api
    .get<RequisitosResp>("/expedientes/requisitos", {
      params: { tipo_proceso },
    })
    .then((r) => r.data);

export interface RequisitosFaltantesResp {
  expediente_id: number;
  tipo_proceso: string;
  completo: boolean;
  faltantes: string[];
  nombres: string[];
}

export const getRequisitosFaltantes = (
  expedienteId: number,
): Promise<RequisitosFaltantesResp> =>
  api
    .get<RequisitosFaltantesResp>(
      `/expedientes/${expedienteId}/requisitos-faltantes`,
    )
    .then((r) => r.data);

export interface PromocionPendienteDTO {
  obra_id: number;
  expediente_id: number | null;
  propietario_id: number;
  nombre_archivo: string;
  tipo_documento: string;
}

/** Cola del supervisor: obrados propuestos para promoverse a jurisprudencia. */
export const listarPromocionesPendientes = (): Promise<
  PromocionPendienteDTO[]
> =>
  api
    .get<PromocionPendienteDTO[]>("/expedientes/promociones-pendientes")
    .then((r) => r.data);
