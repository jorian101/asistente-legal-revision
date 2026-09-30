// Cliente HTTP para chats privados (Sprint 4 — Opcion B fork #133).
//
// Sigue el patron de api/consultas.ts y api/expedientes.ts.
// Endpoints -> rutas de backend/src/routers/chats.py.
//
// Sprint 4 (Opcion B): este backend reemplaza el chatStore localStorage
// del sidebar del Asistente. `consulta_historial` sigue como log inmutable
// de auditoria/KPIs.

import { api } from "./auth";

// ----- DTOs (espejo de response_model de backend/src/routers/chats.py) -----

export interface ChatDTO {
  id: number;
  expediente_id: number | null;
  espacio_trabajo_id: number | null;
  propietario_id: number;
  titulo: string;
  estado: "activo" | "archivado" | "eliminado";
  prioridad: "baja" | "media" | "alta" | "critica";
  contexto_legal:
    | "caso_legal"
    | "audiencia"
    | "reunion"
    | "antecedente"
    | "documento_legal"
    | "consulta_general"
    | null;
  created_at: string | null;
  updated_at: string | null;
  ultimo_mensaje_at: string | null;
}

export interface CrearChatBody {
  /** Omitir o null = chat general sin expediente (solo corpus vectorial). */
  expediente_id?: number | null;
  titulo: string;
  espacio_trabajo_id?: number | null;
  prioridad?: "baja" | "media" | "alta" | "critica";
  contexto_legal?:
    | "caso_legal"
    | "audiencia"
    | "reunion"
    | "antecedente"
    | "documento_legal"
    | "consulta_general";
}

export interface CrearChatResp {
  chat: ChatDTO;
}

export interface MensajeDTO {
  id: number;
  chat_id: number;
  usuario_id: number;
  tipo: "user" | "bot";
  contenido: string;
  razonamiento: string;
  estado: "activo" | "editado" | "eliminado";
  posicion: number;
  created_at: string | null;
}

export interface EnviarMensajeBody {
  tipo: "user" | "bot";
  contenido: string;
  razonamiento?: string;
  metadatos?: Record<string, unknown> | null;
}

export interface PaginaMensajes {
  chat_id: number;
  items: MensajeDTO[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface ArchivarResp {
  chat: ChatDTO;
}

export interface ListarChatsParams {
  expediente_id?: number;
  estado?: "activo" | "archivado" | "eliminado";
}

export interface ListarMensajesParams {
  pagina?: number;
  por_pagina?: number;
}

// ----- Funciones -----

export const listarChats = (
  params: ListarChatsParams = {},
): Promise<ChatDTO[]> =>
  api.get<ChatDTO[]>("/chats/", { params }).then((r) => r.data);

export const crearChat = (body: CrearChatBody): Promise<CrearChatResp> =>
  api.post<CrearChatResp>("/chats/", body).then((r) => r.data);

export const obtenerChat = (chat_id: number): Promise<ChatDTO> =>
  api.get<ChatDTO>(`/chats/${chat_id}`).then((r) => r.data);

export const archivarChat = (chat_id: number): Promise<ArchivarResp> =>
  api.post<ArchivarResp>(`/chats/${chat_id}/archivar`, {}).then((r) => r.data);

export const listarMensajes = (
  chat_id: number,
  params: ListarMensajesParams = {},
): Promise<PaginaMensajes> =>
  api
    .get<PaginaMensajes>(`/chats/${chat_id}/mensajes`, { params })
    .then((r) => r.data);

export const enviarMensaje = (
  chat_id: number,
  body: EnviarMensajeBody,
): Promise<MensajeDTO> =>
  api.post<MensajeDTO>(`/chats/${chat_id}/mensajes`, body).then((r) => r.data);
