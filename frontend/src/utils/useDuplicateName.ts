// Hook utilitario: deteccion de nombres duplicados de conversacion/carpeta.
// Port de useDuplicateNameCheck del reference, adaptado a TS.

import { useMemo } from "react";

import type { Conversacion, EspacioTrabajo } from "../lib/chatTypes";

function tieneNombre(
  items: { nombre?: string; titulo?: string }[],
  nombreBuscado: string,
): boolean {
  if (!nombreBuscado) return false;
  const lower = nombreBuscado.trim().toLowerCase();
  return items.some(
    (it) => (it.nombre ?? it.titulo ?? "").trim().toLowerCase() === lower,
  );
}

export function useDuplicateName(
  conversaciones: Conversacion[],
  espacios: EspacioTrabajo[],
) {
  return useMemo(() => {
    return {
      isDuplicateChatName: (nombre: string) =>
        tieneNombre(
          conversaciones.map((c) => ({ titulo: c.titulo })),
          nombre,
        ),
      isDuplicateFolderName: (nombre: string) =>
        tieneNombre(
          espacios.map((e) => ({ nombre: e.nombre })),
          nombre,
        ),
    };
  }, [conversaciones, espacios]);
}
