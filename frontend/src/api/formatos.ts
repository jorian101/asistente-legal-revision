// Cliente HTTP para el módulo de Formatos TSJM (admin).

import { api } from "./auth";

export interface RunDTO {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  allcaps?: boolean;
  size_pt?: number | null;
  font?: string | null;
}

export interface BloqueDTO {
  page: number;
  index: number;
  kind: string;
  align: string;
  bbox: number[] | null;
  confidence: number;
  review?: boolean;
  overridden?: boolean;
  runs: RunDTO[];
  note?: string;
}

export interface BloqueEsqueletoDTO {
  page: number;
  index: number;
  kind: string;
  align: string;
  template?: boolean;
  texto_plantilla?: string;
  runs: RunDTO[];
}

export interface FormatoDTO {
  id: number;
  tipo_documento: string;
  slug: string;
  autor: string;
  engine: string;
  estado: string;
  version: number;
  meta: Record<string, unknown>;
  bloques: BloqueDTO[];
  esqueleto: BloqueEsqueletoDTO[] | null;
  hash_fuente: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PaginaFormatosDTO {
  items: FormatoDTO[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export async function listarFormatos(params?: {
  tipo_documento?: string;
  autor?: string;
  estado?: string;
  pagina?: number;
  por_pagina?: number;
}): Promise<PaginaFormatosDTO> {
  const { data } = await api.get<PaginaFormatosDTO>("/admin/formatos", {
    params,
  });
  return data;
}

export async function obtenerFormato(id: number): Promise<FormatoDTO> {
  const { data } = await api.get<FormatoDTO>(`/admin/formatos/${id}`);
  return data;
}

export async function obtenerFormatoPorSlug(slug: string): Promise<FormatoDTO> {
  const { data } = await api.get<FormatoDTO>(`/admin/formatos/slug/${slug}`);
  return data;
}

export async function actualizarBloque(
  formatoId: number,
  blockKey: string,
  patch: {
    text?: string;
    align?: string;
    bold?: boolean;
    italic?: boolean;
    underline?: boolean;
    size_pt?: number | null;
    font?: string | null;
    note?: string;
  },
): Promise<FormatoDTO> {
  const { data } = await api.patch<FormatoDTO>(
    `/admin/formatos/${formatoId}/bloques/${blockKey}`,
    patch,
  );
  return data;
}

export async function reordenarBloques(
  formatoId: number,
  orden: string[],
): Promise<FormatoDTO> {
  const { data } = await api.patch<FormatoDTO>(
    `/admin/formatos/${formatoId}/bloques/reordenar`,
    { orden },
  );
  return data;
}

export async function eliminarBloqueApi(
  formatoId: number,
  blockKey: string,
): Promise<FormatoDTO> {
  const { data } = await api.delete<FormatoDTO>(
    `/admin/formatos/${formatoId}/bloques/${blockKey}`,
  );
  return data;
}

export async function promoverFormato(id: number): Promise<FormatoDTO> {
  const { data } = await api.post<FormatoDTO>(`/admin/formatos/${id}/promover`);
  return data;
}

// Persiste config global de página/fuente (lo que el usuario ve en el preview).
export async function actualizarConfiguracion(
  formatoId: number,
  config: {
    tamano_hoja?: string;
    margin_top_mm?: number;
    margin_right_mm?: number;
    margin_bottom_mm?: number;
    margin_left_mm?: number;
    font?: string;
    size_pt?: number;
  },
): Promise<FormatoDTO> {
  const { data } = await api.patch<FormatoDTO>(
    `/admin/formatos/${formatoId}/configuracion`,
    config,
  );
  return data;
}

// Descarga el .docx original de un formato (para el comparador docx-preview).
// Devuelve un blob; null si el formato no proviene de .docx.
export async function obtenerDocxOriginal(id: number): Promise<Blob | null> {
  try {
    const resp = await api.get<Blob>(`/admin/formatos/${id}/original-docx`, {
      responseType: "blob",
    });
    return resp.data;
  } catch {
    return null;
  }
}
