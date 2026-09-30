// persistirChat: sincroniza el chat del Consultar con la BD (chat_privado +
// mensaje_chat). F3: la persistencia ocurre AL ENVIAR (user + bot), no al
// guardar borrador — el backend necesita chat_id desde el primer turno para
// inyectar memoria conversacional.
//
// El chat en vivo sigue viniendo de chatStore (localStorage); la BD es la
// copia que habilita memoria, vinculo borrador<->chat y auditoria.

import { crearChat, enviarMensaje, listarMensajes } from "../api/chats";
import { chatStore } from "./chatStore";

export interface ChatPersistido {
  chatId: number;
  mensajeId: number | null;
}

/**
 * Asegura que la conversacion exista en BD y devuelve su id.
 * Null si la BD falla: la memoria conversacional degrada, el chat sigue.
 */
export async function asegurarChatPersistido(
  usuarioId: number,
  conversacionId: string,
): Promise<number | null> {
  try {
    const conv = chatStore
      .listarConversaciones(usuarioId)
      .find((c) => c.id === conversacionId);
    if (!conv) return null;
    if (conv.chat_id_bd !== null && conv.chat_id_bd !== undefined) {
      return conv.chat_id_bd;
    }
    const resp = await crearChat({
      titulo: conv.titulo || "Sin titulo",
      expediente_id: conv.expediente_id ?? null,
    });
    chatStore.asociarChatBd(usuarioId, conversacionId, resp.chat.id);
    return resp.chat.id;
  } catch {
    return null;
  }
}

/**
 * P2: hidrata el chat local con mensajes persistidos en BD que todavía no
 * existen acá (p. ej. generados desde otra pestaña o dispositivo mientras
 * esta no estaba abierta). Dedupe por `mensaje_id_bd` — nunca pisa
 * contenido local. Devuelve cuántos agregó (0 si el chat no está
 * sincronizado a BD, si la llamada falla, si `omitir()` es true al llegar la
 * respuesta —chat con stream vivo o persistencia pendiente, cuyos mensajes
 * locales todavía no tienen `mensaje_id_bd`— o si no había nada nuevo).
 */
export async function hidratarMensajes(
  usuarioId: number,
  conversacionId: string,
  omitir: () => boolean = () => false,
): Promise<number> {
  try {
    const conv = chatStore
      .listarConversaciones(usuarioId)
      .find((c) => c.id === conversacionId);
    if (!conv || conv.chat_id_bd === null || conv.chat_id_bd === undefined) {
      return 0;
    }
    const pagina = await listarMensajes(conv.chat_id_bd, { por_pagina: 200 });
    if (omitir()) return 0;
    return chatStore.hidratarMensajes(usuarioId, conversacionId, pagina.items);
  } catch {
    return 0;
  }
}

/**
 * Persiste un mensaje (user o bot) en el chat de BD. Devuelve el id BD.
 * No lanza: si la BD falla se pierde solo la memoria, no el chat local.
 */
export async function persistirMensajeEnChat(
  usuarioId: number,
  conversacionId: string,
  tipo: "user" | "bot",
  contenido: string,
): Promise<number | null> {
  try {
    const chatIdBd = await asegurarChatPersistido(usuarioId, conversacionId);
    if (chatIdBd === null || contenido.trim() === "") return null;
    const mensaje = await enviarMensaje(chatIdBd, {
      tipo,
      contenido,
      razonamiento: "",
    });
    return mensaje.id;
  } catch {
    return null;
  }
}
