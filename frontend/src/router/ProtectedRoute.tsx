// ProtectedRoute: bloquea rutas privadas y por rol.
//
// Operate: redirige a /login si no autenticado. Si el rol no matchea,
// redirige a /admin (administrador) o /asistente (resto).
// El backend igual valida autorización; este guard es UX, no seguridad.
//
// requireRol acepta string único (compat) o array de roles permitidos.
// requireModulo exige además permiso "leer" sobre ese módulo del catálogo
// (respeta los overrides por usuario). Mientras cargan sesión o permisos
// muestra un estado de carga (no una pantalla en blanco); si /auth/permisos
// falla, ofrece reintentar.

import { type ReactNode, useContext } from "react";
import { Navigate } from "react-router-dom";

import { Button, StateMessage } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { PermisosContext } from "../context/usePermisos";

type Rol = "administrador" | "supervisor" | "operador_juridico";

interface ProtectedRouteProps {
  children: ReactNode;
  requireRol?: Rol | Rol[];
  requireModulo?: string;
}

export function ProtectedRoute({
  children,
  requireRol,
  requireModulo,
}: ProtectedRouteProps) {
  const { isAuthenticated, auth, cargando } = useAuth();
  const permisosCtx = useContext(PermisosContext);

  // Restaurando la sesion tras un F5: no redirigir todavia.
  if (cargando)
    return <StateMessage tipo="cargando">Cargando sesión…</StateMessage>;

  // Tratar token sin rol (sesión corrupta) como no autenticado.
  // sessionStorage può parziale (rol null) → no es sesión válida real.
  if (!isAuthenticated || auth.rol === null) {
    return <Navigate to="/login" replace />;
  }
  if (requireRol !== undefined) {
    const permitidos = Array.isArray(requireRol) ? requireRol : [requireRol];
    if (!permitidos.includes(auth.rol as Rol)) {
      const fallback = auth.rol === "administrador" ? "/admin" : "/asistente";
      return <Navigate to={fallback} replace />;
    }
  }
  if (requireModulo !== undefined && permisosCtx !== null) {
    if (permisosCtx.permisos === null) {
      return permisosCtx.error ? (
        <StateMessage tipo="error">
          No se pudieron cargar tus permisos.{" "}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void permisosCtx.recargar()}
          >
            Reintentar
          </Button>
        </StateMessage>
      ) : (
        <StateMessage tipo="cargando">Cargando permisos…</StateMessage>
      );
    }
    if (!permisosCtx.puede(requireModulo, "leer")) {
      const raiz = auth.rol === "administrador" ? "/admin" : "/asistente";
      return <Navigate to={raiz} replace />;
    }
  }
  return <>{children}</>;
}
