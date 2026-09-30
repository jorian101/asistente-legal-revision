// Store local de conversaciones de chat (frontend-only).
//
// Persiste en localStorage, scoping por usuario (propietario_id). La API
// publica de este modulo espeja la que Sprint 4 debe exponer via HTTP sobre
// las tablas chat_privado / mensaje_chat / espacio_trabajo ya migradas: al
// reemplazar este modulo por un cliente API, ningun componente deberia
// cambiar su logica.
//
// Clave: "asistente-legal:chats:<usuarioId>".
//
// NOTA Sprint 4: la tabla chat_privado.expediente_id es NOT NULL, pero el
// modulo de expedientes aun no existe. Por eso aqui expediente_id es null
// por defecto. La migracion backend de Sprint 4 debe decidir si relaja esa
// constraint o si el chat siempre vive dentro de un expediente.

import { toast } from "./toasts";
import type {
  Conversacion,
  DocumentoChat,
  EspacioTrabajo,
  FragmentoCita,
  Mensaje,
} from "./chatTypes";

const STORAGE_PREFIX = "asistente-legal:chats";
const NUEVO_ID = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

const AHORA = (): string => new Date().toISOString();

interface EstadoStore {
  conversaciones: Conversacion[];
  mensajes: Mensaje[]; // aplanados (todos los chats), indexados por chat_id
  espacios: EspacioTrabajo[];
  documentos: DocumentoChat[];
}

function clave(usuarioId: number): string {
  return `${STORAGE_PREFIX}:${usuarioId}`;
}

function leerEstado(usuarioId: number): EstadoStore {
  if (typeof localStorage === "undefined") {
    return { conversaciones: [], mensajes: [], espacios: [], documentos: [] };
  }
  const raw = localStorage.getItem(clave(usuarioId));
  if (!raw) {
    return { conversaciones: [], mensajes: [], espacios: [], documentos: [] };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<EstadoStore>;
    return {
      conversaciones: parsed.conversaciones ?? [],
      mensajes: parsed.mensajes ?? [],
      espacios: parsed.espacios ?? [],
      documentos: parsed.documentos ?? [],
    };
  } catch {
    return { conversaciones: [], mensajes: [], espacios: [], documentos: [] };
  }
}

function escribirEstado(usuarioId: number, estado: EstadoStore): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(clave(usuarioId), JSON.stringify(estado));
  } catch {
    // Cuota (~5 MB) llena o storage bloqueado: sin esto la excepción cortaba
    // el stream de la respuesta. El cambio vive en memoria hasta recargar.
    toast(
      "No se pudo guardar el historial local (almacenamiento lleno). Archivá o eliminá conversaciones antiguas.",
      "error",
    );
  }
}

function ensureEspacioPorTipo(
  usuarioId: number,
  estado: EstadoStore,
  tipo: "fijado" | "archivado",
  nombre: string,
): EspacioTrabajo {
  const existente = estado.espacios.find(
    (e) => e.tipo === tipo && e.estado === "activo",
  );
  if (existente) return existente;
  const espacio: EspacioTrabajo = {
    id: NUEVO_ID(),
    expediente_id: null,
    propietario_id: usuarioId,
    nombre,
    tipo,
    estado: "activo",
    created_at: AHORA(),
    updated_at: null,
  };
  estado.espacios.push(espacio);
  return espacio;
}

// ----- API publica ----------------------------------------------------------

export const chatStore = {
  // --- Conversaciones ---

  listarConversaciones(usuarioId: number): Conversacion[] {
    return leerEstado(usuarioId).conversaciones.filter(
      (c) => c.estado !== "eliminado",
    );
  },

  crearConversacion(
    usuarioId: number,
    titulo: string,
    expedienteId: number | null = null,
    espacioTrabajoId: string | null = null,
  ): Conversacion {
    const estado = leerEstado(usuarioId);
    const conversacion: Conversacion = {
      id: NUEVO_ID(),
      expediente_id: expedienteId,
      espacio_trabajo_id: espacioTrabajoId,
      propietario_id: usuarioId,
      titulo: titulo.trim() || "Sin titulo",
      estado: "activo",
      prioridad: "media",
      contexto_legal: null,
      created_at: AHORA(),
      updated_at: null,
      ultimo_mensaje_at: null,
    };
    estado.conversaciones.push(conversacion);
    escribirEstado(usuarioId, estado);
    return conversacion;
  },

  renombrarConversacion(
    usuarioId: number,
    conversacionId: string,
    nuevoTitulo: string,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    conv.titulo = nuevoTitulo.trim() || conv.titulo;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return conv;
  },

  asociarExpediente(
    usuarioId: number,
    conversacionId: string,
    expedienteId: number | null,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    conv.expediente_id = expedienteId;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return conv;
  },

  /** Guarda el id del chat_privado en BD (FK real) para esta conversacion. */
  asociarChatBd(
    usuarioId: number,
    conversacionId: string,
    chatIdBd: number,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    conv.chat_id_bd = chatIdBd;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return conv;
  },

  /** Fija una abreviatura N2/N3 a la conversación (chips, sin duplicar). */
  asociarCorpusRef(
    usuarioId: number,
    conversacionId: string,
    ref: string,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    const actual = conv.corpus_refs ?? [];
    if (!actual.includes(ref)) {
      conv.corpus_refs = [...actual, ref];
      conv.updated_at = AHORA();
      escribirEstado(usuarioId, estado);
    }
    return conv;
  },

  /** Quita una abreviatura N2/N3 fijada (chip ✕). */
  quitarCorpusRef(
    usuarioId: number,
    conversacionId: string,
    ref: string,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    conv.corpus_refs = (conv.corpus_refs ?? []).filter((r) => r !== ref);
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return conv;
  },

  /** Guarda las obras seleccionadas del expediente para la consulta. */
  asociarObras(
    usuarioId: number,
    conversacionId: string,
    obraIds: number[] | null,
  ): Conversacion | null {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return null;
    conv.obra_ids = obraIds;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return conv;
  },

  /** Guarda el id del mensaje (user o bot) en BD (tabla mensaje_chat) para este mensaje local. */
  asociarMensajeBd(
    usuarioId: number,
    mensajeId: string,
    mensajeIdBd: number,
  ): Mensaje | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    msg.metadatos = { ...(msg.metadatos ?? {}), mensaje_id_bd: mensajeIdBd };
    escribirEstado(usuarioId, estado);
    return msg;
  },

  /** Asocia las citas RAG (fuentes) al mensaje bot que las generó. */
  asociarFuentes(
    usuarioId: number,
    mensajeId: string,
    fragmentos: FragmentoCita[],
    scores: number[],
    historialId: number,
  ): Mensaje | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    msg.fragmentos = fragmentos;
    msg.scores = scores;
    msg.historial_id = historialId;
    escribirEstado(usuarioId, estado);
    return msg;
  },

  /** Desvincula la consulta RAG del mensaje (historial borrado en backend). */
  desvincularHistorial(usuarioId: number, mensajeId: string): Mensaje | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    msg.historial_id = undefined;
    escribirEstado(usuarioId, estado);
    return msg;
  },

  /**
   * P2: fusiona mensajes traídos del backend que todavía no existen
   * localmente (dedupe por `mensaje_id_bd` — nunca pisa un mensaje local
   * existente), preservando el orden cronológico real vía `created_at`:
   * cada pestaña numera su propio `posicion` desde 1, así que un mensaje
   * remoto puede intercalarse entre locales y hace falta renumerar todo el
   * chat, no solo anexar al final. Devuelve cuántos mensajes nuevos agregó.
   */
  hidratarMensajes(
    usuarioId: number,
    conversacionId: string,
    remotos: Array<{
      id: number;
      tipo: "user" | "bot";
      contenido: string;
      razonamiento: string;
      created_at: string | null;
    }>,
  ): number {
    const estado = leerEstado(usuarioId);
    const idsBdExistentes = new Set(
      estado.mensajes
        .filter((m) => m.chat_id === conversacionId)
        .map((m) => m.metadatos?.mensaje_id_bd)
        .filter((v): v is number => typeof v === "number"),
    );
    const pendientes = remotos.filter((r) => !idsBdExistentes.has(r.id));
    if (pendientes.length === 0) return 0;

    const localesSinId = estado.mensajes
      .filter(
        (m) =>
          m.chat_id === conversacionId &&
          typeof m.metadatos?.mensaje_id_bd !== "number",
      )
      .sort((a, b) => a.posicion - b.posicion);
    const nuevos = pendientes.filter((r) => {
      const i = localesSinId.findIndex(
        (m) => m.tipo === r.tipo && m.contenido === r.contenido,
      );
      if (i === -1) return true;
      const [local] = localesSinId.splice(i, 1);
      local.metadatos = { ...(local.metadatos ?? {}), mensaje_id_bd: r.id };
      return false;
    });
    if (nuevos.length === 0) {
      escribirEstado(usuarioId, estado);
      return 0;
    }

    let ultimaPosicion = Math.max(
      0,
      ...estado.mensajes
        .filter((m) => m.chat_id === conversacionId)
        .map((m) => m.posicion),
    );
    for (const r of nuevos) {
      estado.mensajes.push({
        id: NUEVO_ID(),
        chat_id: conversacionId,
        tipo: r.tipo,
        razonamiento: r.razonamiento,
        contenido: r.contenido,
        estado: "activo",
        posicion: ++ultimaPosicion, // desempate; se renumera abajo
        metadatos: { mensaje_id_bd: r.id },
        created_at: r.created_at ?? AHORA(),
      });
    }

    estado.mensajes
      .filter((m) => m.chat_id === conversacionId)
      .sort(
        (a, b) =>
          Date.parse(a.created_at) - Date.parse(b.created_at) ||
          a.posicion - b.posicion,
      )
      .forEach((m, i) => {
        m.posicion = i + 1;
      });

    escribirEstado(usuarioId, estado);
    return nuevos.length;
  },

  /** Obtiene el id BD de un mensaje (si ya fue persistido). */
  mensajeIdBdDe(usuarioId: number, mensajeId: string): number | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    const valor = msg.metadatos?.mensaje_id_bd;
    return typeof valor === "number" ? valor : null;
  },

  /** Marca el borrador guardado en el mensaje bot que lo genero. */
  marcarBorradorGuardado(
    usuarioId: number,
    mensajeId: string,
    borradorId: number,
  ): Mensaje | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    msg.borrador_id = borradorId;
    msg.metadatos = { ...(msg.metadatos ?? {}), borrador_id: borradorId };
    escribirEstado(usuarioId, estado);
    return msg;
  },

  /** Obtiene el borrador_id guardado de un mensaje (si ya se guardo). */
  borradorDeMensaje(usuarioId: number, mensajeId: string): number | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    return msg.borrador_id ?? null;
  },

  eliminarConversacion(usuarioId: number, conversacionId: string): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (conv) {
      conv.estado = "eliminado";
      conv.espacio_trabajo_id = null;
      conv.updated_at = AHORA();
    }
    estado.mensajes = estado.mensajes.filter(
      (m) => m.chat_id !== conversacionId,
    );
    escribirEstado(usuarioId, estado);
  },

  archivarConversacion(usuarioId: number, conversacionId: string): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv || conv.estado === "archivado") return;
    const archivos = ensureEspacioPorTipo(
      usuarioId,
      estado,
      "archivado",
      "Archivados",
    );
    conv.estado = "archivado";
    conv.espacio_trabajo_id = archivos.id;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  desarchivarConversacion(usuarioId: number, conversacionId: string): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv || conv.estado !== "archivado") return;
    conv.estado = "activo";
    conv.espacio_trabajo_id = null;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  listarArchivadas(usuarioId: number): Conversacion[] {
    return leerEstado(usuarioId).conversaciones.filter(
      (c) => c.estado === "archivado",
    );
  },

  fijarConversacion(usuarioId: number, conversacionId: string): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return;
    if (conv.estado === "archivado") {
      // Desarchivar implicitamente: no se fija un chat archivado.
      conv.estado = "activo";
    }
    ensureEspacioPorTipo(usuarioId, estado, "fijado", "Fijados");
    conv.espacio_trabajo_id = estado.espacios.find(
      (e) => e.tipo === "fijado" && e.estado === "activo",
    )!.id;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  desfijarConversacion(usuarioId: number, conversacionId: string): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return;
    conv.espacio_trabajo_id = null;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  moverACarpeta(
    usuarioId: number,
    conversacionId: string,
    espacioTrabajoId: string | null,
  ): void {
    const estado = leerEstado(usuarioId);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (!conv) return;
    conv.espacio_trabajo_id = espacioTrabajoId;
    conv.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  // --- Mensajes ---

  listarMensajes(usuarioId: number, conversacionId: string): Mensaje[] {
    return leerEstado(usuarioId)
      .mensajes.filter(
        (m) => m.chat_id === conversacionId && m.estado !== "eliminado",
      )
      .sort((a, b) => a.posicion - b.posicion);
  },

  agregarMensaje(
    usuarioId: number,
    conversacionId: string,
    tipo: "user" | "bot",
    contenido: string,
    extras: Partial<
      Pick<
        Mensaje,
        | "razonamiento"
        | "fragmentos"
        | "scores"
        | "latencia_ms"
        | "tipo_respuesta"
        | "historial_id"
      >
    > = {},
  ): Mensaje {
    const estado = leerEstado(usuarioId);
    const posicion =
      estado.mensajes.filter((m) => m.chat_id === conversacionId).length + 1;
    const mensaje: Mensaje = {
      id: NUEVO_ID(),
      chat_id: conversacionId,
      tipo,
      razonamiento: extras.razonamiento ?? "",
      contenido,
      estado: "activo",
      posicion,
      metadatos: null,
      created_at: AHORA(),
      fragmentos: extras.fragmentos,
      scores: extras.scores,
      latencia_ms: extras.latencia_ms,
      tipo_respuesta: extras.tipo_respuesta,
      historial_id: extras.historial_id,
    };
    estado.mensajes.push(mensaje);
    const conv = estado.conversaciones.find((c) => c.id === conversacionId);
    if (conv) {
      conv.ultimo_mensaje_at = AHORA();
      conv.updated_at = conv.ultimo_mensaje_at;
    }
    escribirEstado(usuarioId, estado);
    return mensaje;
  },

  actualizarMensaje(
    usuarioId: number,
    mensajeId: string,
    contenido: string,
  ): Mensaje | null {
    const estado = leerEstado(usuarioId);
    const msg = estado.mensajes.find((m) => m.id === mensajeId);
    if (!msg) return null;
    msg.contenido = contenido;
    escribirEstado(usuarioId, estado);
    return msg;
  },

  // --- Espacios de trabajo (carpetas) ---

  listarEspacios(usuarioId: number): EspacioTrabajo[] {
    return leerEstado(usuarioId).espacios.filter(
      (e) => e.estado !== "eliminado",
    );
  },

  listarEspaciosConChats(
    usuarioId: number,
  ): Array<EspacioTrabajo & { chats: Conversacion[] }> {
    const estado = leerEstado(usuarioId);
    const espacios = estado.espacios.filter((e) => e.estado !== "eliminado");
    return espacios.map((espacio) => ({
      ...espacio,
      chats: estado.conversaciones.filter(
        (c) => c.espacio_trabajo_id === espacio.id && c.estado === "activo",
      ),
    }));
  },

  crearEspacio(usuarioId: number, nombre: string): EspacioTrabajo {
    const estado = leerEstado(usuarioId);
    const espacio: EspacioTrabajo = {
      id: NUEVO_ID(),
      expediente_id: null,
      propietario_id: usuarioId,
      nombre: nombre.trim() || "Sin titulo",
      tipo: "personalizado",
      estado: "activo",
      created_at: AHORA(),
      updated_at: null,
    };
    estado.espacios.push(espacio);
    escribirEstado(usuarioId, estado);
    return espacio;
  },

  renombrarEspacio(
    usuarioId: number,
    espacioId: string,
    nuevoNombre: string,
  ): EspacioTrabajo | null {
    const estado = leerEstado(usuarioId);
    const espacio = estado.espacios.find((e) => e.id === espacioId);
    if (!espacio) return null;
    espacio.nombre = nuevoNombre.trim() || espacio.nombre;
    espacio.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
    return espacio;
  },

  eliminarEspacio(usuarioId: number, espacioId: string): void {
    const estado = leerEstado(usuarioId);
    const espacio = estado.espacios.find((e) => e.id === espacioId);
    if (!espacio || espacio.tipo === "fijado") return; // Fijados no se elimina
    // Mover chats sueltos a la zona principal (espacio_trabajo_id = null).
    for (const conv of estado.conversaciones) {
      if (conv.espacio_trabajo_id === espacioId) {
        conv.espacio_trabajo_id = null;
        conv.updated_at = AHORA();
      }
    }
    espacio.estado = "eliminado";
    espacio.updated_at = AHORA();
    escribirEstado(usuarioId, estado);
  },

  // --- Busqueda (cliente-side) ---

  buscarConversaciones(usuarioId: number, query: string): Conversacion[] {
    const estado = leerEstado(usuarioId);
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return estado.conversaciones.filter(
      (c) =>
        c.estado !== "eliminado" &&
        (c.titulo.toLowerCase().includes(q) ||
          estado.mensajes.some(
            (m) =>
              m.chat_id === c.id &&
              m.estado !== "eliminado" &&
              m.contenido.toLowerCase().includes(q),
          )),
    );
  },
};
