// PermisosProvider: carga /auth/permisos y expone los permisos efectivos del
// usuario logueado (sidebar dinámico — Fase 2 del plan permisos-crud-modulos).
//
// Recarga cuando cambia el usuario (id/rol), NO en cada refresh del access
// token: vaciar los permisos cada hora desmontaba las rutas `requireModulo`.
// `permisos` es null mientras carga; los layouts deben tener un fallback
// (matriz por rol) para ese estado.

import { type ReactNode, useEffect, useMemo, useState } from "react";

import { type ModuloPermisoDTO, obtenerPermisosPropios } from "../api/permisos";

import { useAuth } from "./useAuth";
import {
  PermisosContext,
  type OperacionCRUD,
  type PermisosContextValue,
} from "./usePermisos";

export function PermisosProvider({ children }: { children: ReactNode }) {
  const { auth } = useAuth();
  const [permisos, setPermisos] = useState<ModuloPermisoDTO[] | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState(false);
  const autenticado = auth.access_token !== null;

  useEffect(() => {
    let cancelado = false;
    setPermisos(null);
    setError(false);
    if (!autenticado) {
      return;
    }
    obtenerPermisosPropios()
      .then((data) => {
        if (!cancelado) setPermisos(data);
      })
      .catch(() => {
        // Falla silenciosa: dejar null para que los layouts usen el fallback
        // por rol (no un sidebar vacío).
        if (!cancelado) {
          setPermisos(null);
          setError(true);
        }
      });
    return () => {
      cancelado = true;
    };
  }, [autenticado, auth.id, auth.rol, version]);

  const value = useMemo<PermisosContextValue>(
    () => ({
      permisos,
      error,
      puede(clave: string, operacion: OperacionCRUD): boolean {
        if (permisos === null) return false; // cargando o fallo: cerrado
        const modulo = permisos.find((m) => m.clave === clave);
        if (modulo === undefined) return false;
        return modulo[`puede_${operacion}`];
      },
      async recargar() {
        setVersion((v) => v + 1);
      },
    }),
    [permisos, error],
  );

  return (
    <PermisosContext.Provider value={value}>
      {children}
    </PermisosContext.Provider>
  );
}
