// Cliente HTTP para la gestión del Corpus Jurídico (Sprint 2).
//
// Sigue el patrón de api/auth.ts: usa el cliente `api` (baseURL /api,
// Authorization header + retry refresh en 401 ya configurados).
// Endpoints admin → rutas de backend/src/routers/corpus.py.

import { api, conProgreso } from "./auth";
import type { TrabajoEncolado } from "./jobs";

// DTOs (espejo de los response_model de backend/src/routers/corpus.py)

export interface NormaDTO {
  norma_id: number;
  abreviatura: string;
  nombre: string;
  tipo: string;
  jerarquia: string;
  version: string | null;
  indexado: boolean;
  indexado_por: number | null;
}

export interface CandidatoPatronDTO {
  abreviatura: string;
  articulos_matcheados: number;
  confianza: number;
}

export interface DeteccionPatronesDTO {
  mejor: string | null;
  confianza: number;
  candidatos: CandidatoPatronDTO[];
  error: string | null;
}

export interface EndpointEmbeddingDTO {
  id: string;
  provider: string;
  model: string;
  dim: number;
}

export interface FragmentoDTO {
  id: number;
  norma_id: number | null;
  qdrant_point_id: string;
  texto: string;
  padre_ref_key: string | null;
  nivel_jerarquico: number | null;
  tipo_chunk: string | null;
}

export interface EndpointModeloDTO {
  id: string;
  provider: string;
  model: string;
}

export interface PaginaFragmentosDTO {
  items: FragmentoDTO[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export type OrdenNormas =
  "abreviatura" | "nombre" | "tipo" | "jerarquia" | "indexado";

export const listarNormas = (
  orden: OrdenNormas = "abreviatura",
): Promise<NormaDTO[]> =>
  api
    .get<NormaDTO[]>("/admin/corpus/normas", { params: { orden } })
    .then((r) => r.data);

export const listarEndpointsEmbedding = (): Promise<EndpointEmbeddingDTO[]> =>
  api
    .get<EndpointEmbeddingDTO[]>("/admin/corpus/endpoints-embedding")
    .then((r) => r.data);

/** La indexacion se encola: 202 con el job_id, que se sigue en /jobs/{job_id}. */
export const indexarNorma = (
  abreviatura: string,
  file: File,
  version?: string,
  endpointId?: string,
  onProgreso?: (pct: number) => void,
): Promise<TrabajoEncolado> => {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("abreviatura", abreviatura);
  if (version) fd.append("version", version);
  if (endpointId) fd.append("endpoint_id", endpointId);
  return api
    .post<TrabajoEncolado>("/admin/corpus/normas", fd, conProgreso(onProgreso))
    .then((r) => r.data);
};

export const listarFragmentos = (params: {
  pagina?: number;
  por_pagina?: number;
  norma_id?: number;
  tipo_chunk?: string;
  nivel?: number;
  texto?: string;
}): Promise<PaginaFragmentosDTO> =>
  api
    .get<PaginaFragmentosDTO>("/admin/corpus/fragmentos", { params })
    .then((r) => r.data);

export const reconciliarCorpus = (): Promise<{
  pg_count: number;
  qdrant_count: number;
  huerfanos_eliminados: number;
}> => api.post("/admin/corpus/reconciliar").then((r) => r.data);

// F1.4: detección de patrones (dry-run, no persiste).
export const detectarPatrones = (file: File): Promise<DeteccionPatronesDTO> => {
  const fd = new FormData();
  fd.append("file", file);
  return api
    .post<DeteccionPatronesDTO>("/admin/corpus/detectar-patrones", fd)
    .then((r) => r.data);
};

// ----- Configuración RAG: endpoints de modelos (Sprint 3/6) -----

export const listarEndpointsReranker = (): Promise<EndpointModeloDTO[]> =>
  api
    .get<EndpointModeloDTO[]>("/admin/corpus/endpoints-reranker")
    .then((r) => r.data);

export const obtenerRerankerSeleccionado = (): Promise<EndpointModeloDTO> =>
  api
    .get<EndpointModeloDTO>("/admin/corpus/configuracion-rag/reranker-endpoint")
    .then((r) => r.data);

export const seleccionarReranker = (
  endpointId: string | null,
): Promise<EndpointModeloDTO> =>
  api
    .put<EndpointModeloDTO>(
      "/admin/corpus/configuracion-rag/reranker-endpoint",
      { endpoint_id: endpointId },
    )
    .then((r) => r.data);

export const listarEndpointsLLM = (): Promise<EndpointModeloDTO[]> =>
  api
    .get<EndpointModeloDTO[]>("/admin/corpus/endpoints-llm")
    .then((r) => r.data);

export const obtenerLLMSeleccionado = (): Promise<EndpointModeloDTO> =>
  api
    .get<EndpointModeloDTO>("/admin/corpus/configuracion-rag/llm-endpoint")
    .then((r) => r.data);

export const seleccionarLLM = (
  endpointId: string | null,
): Promise<EndpointModeloDTO> =>
  api
    .put<EndpointModeloDTO>("/admin/corpus/configuracion-rag/llm-endpoint", {
      endpoint_id: endpointId,
    })
    .then((r) => r.data);

export interface NormalizarQueryDTO {
  activado: boolean;
}

export const obtenerNormalizarQuery = (): Promise<NormalizarQueryDTO> =>
  api
    .get<NormalizarQueryDTO>("/admin/corpus/configuracion-rag/normalizar-query")
    .then((r) => r.data);

export const setNormalizarQuery = (
  activado: boolean,
): Promise<NormalizarQueryDTO> =>
  api
    .put<NormalizarQueryDTO>(
      "/admin/corpus/configuracion-rag/normalizar-query",
      {
        activado,
      },
    )
    .then((r) => r.data);

// ----- Configuración RAG: umbrales ajustables (HU-23) -----

export interface ConfiguracionRAGDTO {
  score_threshold: number;
  top_k_denso: number;
  top_k_lexico: number;
  top_k_final: number;
  max_profundidad_bfs: number;
  top_k_padres_a_incluir: number;
  temperatura: number;
  modelo_embeddings: string;
  modelo_llm_default: string;
  normalizar_query: boolean;
  reranker_endpoint_id: string | null;
  llm_endpoint_id: string | null;
  actualizado_por: number | null;
  updated_at: string | null;
}

export type AjusteParametrosDTO = Partial<
  Pick<
    ConfiguracionRAGDTO,
    | "score_threshold"
    | "top_k_denso"
    | "top_k_lexico"
    | "top_k_final"
    | "max_profundidad_bfs"
    | "top_k_padres_a_incluir"
    | "temperatura"
  >
>;

export const obtenerConfiguracionRAG = (): Promise<ConfiguracionRAGDTO> =>
  api
    .get<ConfiguracionRAGDTO>("/admin/corpus/configuracion-rag")
    .then((r) => r.data);

export const ajustarParametrosRAG = (
  valores: AjusteParametrosDTO,
): Promise<ConfiguracionRAGDTO> =>
  api
    .patch<ConfiguracionRAGDTO>("/admin/corpus/configuracion-rag", valores)
    .then((r) => r.data);

export const editarNorma = (
  normaId: number,
  data: { nombre?: string; version?: string },
): Promise<NormaDTO> =>
  api
    .patch<NormaDTO>(`/admin/corpus/normas/${normaId}`, data)
    .then((r) => r.data);

export const eliminarNorma = (normaId: number): Promise<void> =>
  api.delete(`/admin/corpus/normas/${normaId}`).then(() => undefined);
