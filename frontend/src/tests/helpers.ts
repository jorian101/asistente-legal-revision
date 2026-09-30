// Helpers compartidos de testing frontend.
// Convenciones completas: docs/testing.md.

import { fireEvent } from "@testing-library/react";

import type { PermisosContextValue } from "../context/usePermisos";

/**
 * Asigna múltiples archivos a un input[type=file] y dispara change.
 *
 * userEvent.upload múltiple solo entregó 1 archivo al onChange en este
 * setup (jsdom + user-event v14) — este patrón define el FileList y
 * dispara el evento manualmente, entregando todos los archivos.
 */
export function asignarArchivos(input: HTMLInputElement, files: File[]): void {
  Object.defineProperty(input, "files", {
    value: files,
    configurable: true,
  });
  fireEvent.change(input);
}

/**
 * Valor de PermisosContext para tests: todo permitido salvo las operaciones
 * listadas como "modulo.operacion" (ej. "obras.eliminar").
 */
export function permisosDeTest(denegados: string[] = []): PermisosContextValue {
  return {
    permisos: [],
    puede: (clave, operacion) => !denegados.includes(`${clave}.${operacion}`),
    recargar: async () => {},
  };
}
