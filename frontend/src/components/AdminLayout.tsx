// AdminLayout: NavRail fijo + Outlet. Envuelve todas las rutas /admin/*.
// El menú viene de /auth/permisos; mientras cargan, fallback a la matriz
// del rol administrador.

import { usePermisos } from "../context/usePermisos";
import {
  modulosAccesoParaRol,
  modulosDesdePermisos,
} from "../config/modulosPorRol";
import { AppShell } from "./AppShell";

export function AdminLayout() {
  const { permisos } = usePermisos();

  const modulos =
    permisos === null
      ? modulosAccesoParaRol("administrador")
      : modulosDesdePermisos(
          permisos.filter((p) => p.ruta.startsWith("/admin/")),
          "admin",
        );

  return <AppShell modulos={modulos} raiz="/admin" />;
}
