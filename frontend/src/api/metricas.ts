// Cliente HTTP para métricas de contexto (HU-22 / Fase C2).
//
// Espejo de backend/src/routers/admin_metricas.py — GET /admin/metricas/contexto.
// Solo admin (require_admin en el backend).

import { api } from "./auth";

export interface MetricaItemDTO {
  consulta_id: number;
  usuario_id: number;
  latencia_expansion_ms: number;
  nodos_ascendidos: number;
  breadcrumbs_count: number;
  expansion_realizada: boolean;
}

export interface MetricasContextoDTO {
  total_consultas: number;
  expansion_realizada_count: number;
  latencia_expansion_promedio_ms: number;
  nodos_ascendidos_promedio: number;
  breadcrumbs_count_promedio: number;
  iteraciones: MetricaItemDTO[];
}

export const obtenerMetricasContexto = (
  limite: number = 100,
): Promise<MetricasContextoDTO> =>
  api
    .get<MetricasContextoDTO>("/admin/metricas/contexto", {
      params: { limite },
    })
    .then((r) => r.data);

// ----- Dashboard admin (resumen general de chats y modelos) -----

export interface ResumenTipoDTO {
  tipo_respuesta: string;
  cantidad: number;
}

export interface ResumenModeloDTO {
  modelo_llm: string | null;
  cantidad: number;
  latencia_promedio_ms: number | null;
}

export interface ResumenUsuarioDTO {
  usuario_id: number;
  usuario_carnet: string;
  usuario_nombre: string;
  cantidad: number;
}

export interface ResumenDiaDTO {
  fecha: string;
  cantidad: number;
}

export interface EndpointActivoDTO {
  id: string;
  provider: string;
  model: string;
}

export interface DashboardResumenDTO {
  total_consultas: number;
  en_progreso: number;
  completadas: number;
  con_error: number;
  por_tipo: ResumenTipoDTO[];
  por_modelo: ResumenModeloDTO[];
  por_usuario: ResumenUsuarioDTO[];
  consultas_por_dia: ResumenDiaDTO[];
  llm_endpoint: EndpointActivoDTO | null;
  embedding_endpoint: EndpointActivoDTO | null;
  reranker_endpoint: EndpointActivoDTO | null;
}

export const obtenerResumenDashboard = (): Promise<DashboardResumenDTO> =>
  api.get<DashboardResumenDTO>("/admin/dashboard/resumen").then((r) => r.data);

// ----- Salud de infraestructura (HU-22) -----

export interface MetricasSaludDTO {
  postgres_ok: boolean;
  qdrant_ok: boolean;
  qdrant_puntos: number;
  sesiones_activas: number;
}

export const obtenerSaludSistema = (): Promise<MetricasSaludDTO> =>
  api.get<MetricasSaludDTO>("/admin/metricas/salud").then((r) => r.data);

// ----- Auditoria (Trail of Bits R6) -----

export interface AuditoriaItemDTO {
  accion: string;
  entidad: string | null;
  entidad_id: number | null;
  usuario_id: number | null;
  detalle: Record<string, unknown> | null;
  created_at: string | null;
}

export interface PaginaAuditoriaDTO {
  items: AuditoriaItemDTO[];
  total: number;
}

export const listarAuditoria = (
  accion?: string,
  limite: number = 100,
): Promise<PaginaAuditoriaDTO> =>
  api
    .get<PaginaAuditoriaDTO>("/admin/auditoria", {
      params: { accion, limite },
    })
    .then((r) => r.data);
