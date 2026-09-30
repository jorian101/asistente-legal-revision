// usePermisos.ts: define el Context + el hook.
// PermisosContext.tsx solo exporta el Provider que consume este Context.

import { createContext, useContext } from "react";

import { type ModuloPermisoDTO } from "../api/permisos";

export type OperacionCRUD = "crear" | "leer" | "actualizar" | "eliminar";

export interface PermisosContextValue {
  /** Módulos activos con permisos efectivos del usuario. null = cargando. */
  permisos: ModuloPermisoDTO[] | null;
  /** True si /auth/permisos falló (permisos queda en null). */
  error?: boolean;
  /** True si el usuario tiene la operación CRUD sobre el módulo. */
  puede: (clave: string, operacion: OperacionCRUD) => boolean;
  /** Recarga /auth/permisos (tras un cambio de permisos en otra pestaña). */
  recargar: () => Promise<void>;
}

export const PermisosContext = createContext<PermisosContextValue | null>(null);

export function usePermisos(): PermisosContextValue {
  const ctx = useContext(PermisosContext);
  if (ctx === null) {
    throw new Error("usePermisos debe usarse dentro de PermisosProvider");
  }
  return ctx;
}
