// Agrupacion de conversaciones por fecha para el sidebar.
// Port de groupChatsByDate del reference tribsupjusmil, tipado en TS.

import type { Conversacion } from "../lib/chatTypes";

export interface GruposPorFecha {
  hoy: Conversacion[];
  ayer: Conversacion[];
  ultimos7dias: Conversacion[];
  esteMes: Conversacion[];
  meses: Record<string, Conversacion[]>;
  anios: Record<string, Conversacion[]>;
}

export const GROUP_LABELS: Record<
  "hoy" | "ayer" | "ultimos7dias" | "esteMes",
  string
> = {
  hoy: "Hoy",
  ayer: "Ayer",
  ultimos7dias: "Ultimos 7 dias",
  esteMes: "Este mes",
};

function toDate(chat: Conversacion): Date {
  const raw = chat.ultimo_mensaje_at ?? chat.updated_at ?? chat.created_at;
  return new Date(raw);
}

export function groupConversacionesPorFecha(
  chats: Conversacion[],
): GruposPorFecha {
  const groups: GruposPorFecha = {
    hoy: [],
    ayer: [],
    ultimos7dias: [],
    esteMes: [],
    meses: {},
    anios: {},
  };
  const now = new Date();
  const today = now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const yesterdayStr = yesterday.toDateString();

  for (const chat of chats) {
    const dateObj = toDate(chat);
    if (Number.isNaN(dateObj.getTime())) continue;
    const chatDateStr = dateObj.toDateString();
    const diffDays = Math.floor(
      (now.getTime() - dateObj.getTime()) / (1000 * 60 * 60 * 24),
    );
    const year = dateObj.getFullYear();
    const month = dateObj.getMonth() + 1;
    const monthStr = `${year}-${month.toString().padStart(2, "0")}`;

    if (chatDateStr === today) {
      groups.hoy.push(chat);
    } else if (chatDateStr === yesterdayStr) {
      groups.ayer.push(chat);
    } else if (diffDays < 7) {
      groups.ultimos7dias.push(chat);
    } else if (year === now.getFullYear() && month === now.getMonth() + 1) {
      groups.esteMes.push(chat);
    } else if (year === now.getFullYear()) {
      (groups.meses[monthStr] ??= []).push(chat);
    } else {
      (groups.anios[String(year)] ??= []).push(chat);
    }
  }
  return groups;
}

export function getMonthName(month: number, year: number): string {
  return new Date(year, month - 1, 1).toLocaleString("es-BO", {
    month: "long",
    year: "numeric",
  });
}

/** Ordena conversaciones por fecha mas reciente primero (in-place). */
export function ordenarPorFechaDesc(chats: Conversacion[]): Conversacion[] {
  return chats.sort((a, b) => {
    const aDate = toDate(a).getTime();
    const bDate = toDate(b).getTime();
    return bDate - aDate;
  });
}
