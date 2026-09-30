// Tipos del modelo de conversaciones de chat (frontend-only).
//
// Espejo de las tablas ya migradas en la DB del proyecto (migracion
// 8f345a460a82): chat_privado, mensaje_chat, espacio_trabajo, documento_chat.
// Sprint 4 conectara estos tipos a un backend real (/chats) que reemplazara
// el store local (lib/chatStore.ts) por llamadas HTTP.
//
// Mapeo de tablas ↔ tipos:
//   espacio_trabajo (tipo fijado/archivado/personalizado) ↔ EspacioTrabajo
//   chat_privado (estado activo/archivado/eliminado, prioridad) ↔ Conversacion
//   mensaje_chat (tipo user/bot, razonamiento, posicion)   ↔ Mensaje
//   documento_chat                                          ↔ DocumentoChat

export type EstadoConversacion = "activo" | "archivado" | "eliminado";

export type TipoEspacio = "fijado" | "archivado" | "personalizado";

export type TipoMensaje = "user" | "bot";

export type PrioridadConversacion = "baja" | "media" | "alta" | "critica";

export interface EspacioTrabajo {
  id: string;
  /** FK al expediente (Sprint 4). */
  expediente_id: number | null;
  /** Propietario = usuario autenticado. */
  propietario_id: number;
  nombre: string;
  tipo: TipoEspacio;
  estado: "activo" | "eliminado";
  created_at: string;
  updated_at: string | null;
}

export interface DocumentoChat {
  id: string;
  /** Id del chat al que pertenece (chat_privado.id). */
  chat_id: string;
  /** Id del mensaje que lo acompana (mensaje_chat.id). */
  mensaje_id: string | null;
  usuario_id: number;
  nombre_original: string;
  tamano_archivo: number;
  tipo_documento: string;
  estado_procesamiento: "pendiente" | "procesando" | "completado" | "fallido";
  uploaded_at: string;
}

/** Fragmento RAG recuperado en una consulta (ContextoRecuperado del backend). */
/** Fragmento citable del mensaje bot (sanitizado en backend, sin refs técnicas). */
export interface FragmentoCita {
  id: number | null;
  norma_id: number | null;
  obra_id: number | null;
  texto: string;
  /** Referencia jerárquica legible (ej. "LOJM 3"). Null si no hay clave. */
  referencia: string | null;
  nivel_jerarquico: number | null;
  /** Enriquecimiento (resuelto en backend): nombre/abreviatura de norma. */
  norma_nombre?: string | null;
  norma_abreviatura?: string | null;
  /** Tipo de pieza procesal de la obra (ej. "auto_vista"). */
  obra_tipo?: string | null;
  /** Fecha del documento de la obra, si la tiene. */
  obra_fecha_documento?: string | null;
  /** Número de caso del expediente de la obra (ej. "3349"). */
  expediente_numero?: string | null;
  /** Categoría decidida por el backend: norma | jurisprudencia | doctrina | obrado. */
  categoria?: string | null;
}

export interface Mensaje {
  id: string;
  /** FK al chat al que pertenece. */
  chat_id: string;
  /** Quien lo escribio. user = el operador, bot = la respuesta del pipeline. */
  tipo: TipoMensaje;
  razonamiento: string;
  contenido: string;
  estado: "activo" | "editado" | "eliminado";
  posicion: number;
  metadatos: Record<string, unknown> | null;
  created_at: string;
  /** Fragmentos RAG recuperados en este turno (Solo mensajes bot). */
  fragmentos?: FragmentoCita[];
  /** Scores de los fragmentos, alineados con `fragmentos`. */
  scores?: number[];
  /** Latencia del pipeline en ms (mensajes bot). */
  latencia_ms?: number | null;
  tipo_respuesta?: string | null;
  /** Id del historial persistido en consulta_historial (Sprint 3). */
  historial_id?: number;
  /** Id del borrador guardado de este turno (null si no se guardó aún). */
  borrador_id?: number | null;
}

export interface Conversacion {
  id: string;
  /** Sprint 4: FK al expediente. null mientras este modulo no dependa de uno. */
  expediente_id: number | null;
  /** Sprint 4: FK a espacio_trabajo (carpeta). */
  espacio_trabajo_id: string | null;
  propietario_id: number;
  titulo: string;
  estado: EstadoConversacion;
  prioridad: PrioridadConversacion;
  contexto_legal: string | null;
  created_at: string;
  updated_at: string | null;
  ultimo_mensaje_at: string | null;
  /** Id del chat_privado en BD (FK real). Se crea al guardar un borrador. */
  chat_id_bd?: number | null;
  /** Obras del expediente seleccionadas para la consulta (todas si null). */
  obra_ids?: number[] | null;
  /** Abreviaturas N2/N3 fijadas ad-hoc (T2 chips, sin crear puntero). */
  corpus_refs?: string[] | null;
}
