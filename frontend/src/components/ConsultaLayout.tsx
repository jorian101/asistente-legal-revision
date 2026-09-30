// ConsultaLayout: layout del asistente jurídico (bounded context separado
// de AdminLayout). NavRail fijo + Outlet. Usado por /asistente/*.
//
// El menú viene de /auth/permisos; mientras cargan, fallback por rol.
// En /asistente/consultar el contenido va a sangre (el panel de historial
// vive dentro de la página, no aquí).

import { useLocation } from "react-router-dom";

import { useAuth } from "../context/useAuth";
import { usePermisos } from "../context/usePermisos";
import {
  esDeArea,
  modulosDesdePermisos,
  modulosParaRol,
} from "../config/modulosPorRol";
import { AppShell } from "./AppShell";

export function ConsultaLayout() {
  const { auth } = useAuth();
  const { permisos } = usePermisos();
  const location = useLocation();

  const modulos =
    permisos === null
      ? modulosParaRol(auth.rol)
      : modulosDesdePermisos(
          permisos.filter((p) => esDeArea(p, "asistente")),
          "asistente",
        );

  return (
    <AppShell
      modulos={modulos}
      raiz="/asistente"
      sinPadding={location.pathname === "/asistente/consultar"}
    />
  );
}
