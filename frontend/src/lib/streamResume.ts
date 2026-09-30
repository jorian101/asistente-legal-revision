// streamResume: reanudación de streams interrumpidos por recarga.
//
// Al iniciar un stream se guarda el pendiente en sessionStorage (sobrevive
// a recarga y a logout→login en la misma pestaña). Al montar el chat se
// polea el detalle del historial con backoff hasta respuesta final o
// timeout; el backend ya persistió lo completado (productor desacoplado).

import { obtenerHistorialDetalle } from "../api/consultas";

export interface StreamPendiente {
  historialId: number;
  chatId: string;
  pregunta: string;
  ts: number;
}

const CLAVE = "vlc_stream_pendiente";

export function guardarPendiente(p: StreamPendiente): void {
  try {
    sessionStorage.setItem(CLAVE, JSON.stringify(p));
  } catch {
    // sessionStorage lleno o bloqueado: sin reanudación, sin romper nada.
  }
}

export function leerPendiente(): StreamPendiente | null {
  try {
    const raw = sessionStorage.getItem(CLAVE);
    if (!raw) return null;
    const p = JSON.parse(raw) as StreamPendiente;
    if (typeof p.historialId !== "number") return null;
    return p;
  } catch {
    return null;
  }
}

/**
 * F2: si se pasa `historialId`, solo limpia cuando el pendiente guardado
 * ES ese — dos chats generando a la vez comparten esta única ranura
 * (sessionStorage), así que el que termina primero no debe borrar el
 * pendiente del que sigue generando. Sin argumento, limpia sin condición
 * (uso explícito del usuario, p. ej. al cancelar a mano).
 */
export function limpiarPendiente(historialId?: number): void {
  try {
    if (historialId !== undefined) {
      const actual = leerPendiente();
      if (actual && actual.historialId !== historialId) return;
    }
    sessionStorage.removeItem(CLAVE);
  } catch {
    // noop
  }
}

const ESPERAS_MS = [2000, 3000, 5000, 8000, 8000, 10000];
const MAX_INTENTOS = 12;

/**
 * P1: decide por `estado`, NO por `respuesta` no vacía — el backend persiste
 * el parcial en vivo (throttled) mientras `estado` sigue 'en_progreso', así
 * que `det.respuesta` truthy ya no significa "terminó". `onParcial` se
 * invoca en cada poll mientras sigue en curso, para poder mostrar el texto
 * escribiéndose sin esperar al cierre.
 */
export async function esperarRespuestaFinal(
  historialId: number,
  cancelado?: () => boolean,
  onParcial?: (texto: string) => void,
): Promise<{ respuesta: string } | { error: string }> {
  for (let i = 0; i < MAX_INTENTOS; i++) {
    if (cancelado?.()) return { error: "cancelado" };
    try {
      const det = await obtenerHistorialDetalle(historialId);
      if (det.estado === "error") {
        return { error: "La consulta terminó con error en el servidor." };
      }
      if (det.estado === "completado") {
        return { respuesta: det.respuesta ?? "" };
      }
      // 'en_progreso' (o estado desconocido): seguir polleando; el parcial
      // ya persistido se muestra si hay algo escrito.
      if (det.respuesta) {
        onParcial?.(det.respuesta);
      }
    } catch {
      // Red caída o 404: se reintenta hasta agotar intentos.
    }
    await new Promise((r) =>
      setTimeout(r, ESPERAS_MS[Math.min(i, ESPERAS_MS.length - 1)]),
    );
  }
  return { error: "La respuesta no terminó a tiempo. Reintente la consulta." };
}
