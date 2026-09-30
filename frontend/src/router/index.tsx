// Router principal de la app.

import { lazy, type JSX } from "react";
import {
  Navigate,
  Route,
  RouterProvider,
  createBrowserRouter,
  createRoutesFromElements,
} from "react-router-dom";

import { AuthProvider } from "../context/AuthContext";
import { PermisosProvider } from "../context/PermisosContext";
import { ProtectedRoute } from "./ProtectedRoute";
import { AdminLayout } from "../components/AdminLayout";
import { ConsultaLayout } from "../components/ConsultaLayout";
import { SidebarProvider } from "../components/chat/ChatSidebarContext";
import { useAuth } from "../context/useAuth";
import Login from "../pages/Login";

// Cada página va en su propio chunk: el operador no descarga tiptap ni
// docx-preview (admin) y el primer render solo trae shell + login.
const AdminDashboard = lazy(() => import("../pages/admin/Dashboard"));
const Usuarios = lazy(() => import("../pages/admin/Usuarios"));
const Corpus = lazy(() => import("../pages/admin/Corpus"));
const Metricas = lazy(() => import("../pages/admin/Metricas"));
const SalaControl = lazy(() => import("../pages/admin/SalaControl"));
const Auditoria = lazy(() => import("../pages/admin/Auditoria"));
const ConsultasHistorial = lazy(
  () => import("../pages/admin/ConsultasHistorial"),
);
const Modulos = lazy(() => import("../pages/admin/Modulos"));
const PermisosUsuario = lazy(() => import("../pages/admin/PermisosUsuario"));
const Criterios = lazy(() => import("../pages/admin/Criterios"));
const Fuentes = lazy(() => import("../pages/consultas/Fuentes"));
const Formatos = lazy(() => import("../pages/admin/Formatos"));
const Asistente = lazy(() => import("../pages/consultas/Asistente"));
const ConsultaDashboard = lazy(() => import("../pages/consultas/Dashboard"));
const Conversaciones = lazy(() => import("../pages/consultas/Conversaciones"));
const Expedientes = lazy(() => import("../pages/consultas/Expedientes"));
const Borradores = lazy(() => import("../pages/consultas/Borradores"));
const Perfil = lazy(() => import("../pages/Perfil"));

// Data router (createBrowserRouter): habilita useBlocker para avisar antes de
// navegar con cambios sin guardar. Mismas rutas, guards y redirects por rol
// que el <BrowserRouter> anterior. Se crea una sola vez al cargar el módulo.
const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<Login />} />
      <Route
        path="/admin"
        element={
          <ProtectedRoute requireRol="administrador">
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<AdminDashboard />} />
        <Route path="usuarios" element={<Usuarios />} />
        <Route path="corpus" element={<Corpus />} />
        <Route path="metricas" element={<Metricas />} />
        <Route path="sala-control" element={<SalaControl />} />
        <Route path="auditoria" element={<Auditoria />} />
        <Route path="consultas" element={<ConsultasHistorial />} />
        <Route path="modulos" element={<Modulos />} />
        <Route path="permisos" element={<PermisosUsuario />} />
        <Route path="criterios" element={<Criterios />} />
        <Route path="formatos" element={<Formatos />} />
        <Route path="perfil" element={<Perfil />} />
        {/* Slots futuros — Sprint 4+:
              <Route path="expedientes" element={<Expedientes />} />
            */}
      </Route>
      <Route
        path="/asistente"
        element={
          <ProtectedRoute requireRol={["supervisor", "operador_juridico"]}>
            <SidebarProvider>
              <ConsultaLayout />
            </SidebarProvider>
          </ProtectedRoute>
        }
      >
        <Route index element={<ConsultaDashboard />} />
        <Route
          path="consultar"
          element={
            <ProtectedRoute requireModulo="consultar">
              <Asistente />
            </ProtectedRoute>
          }
        />
        <Route
          path="conversaciones"
          element={
            <ProtectedRoute requireModulo="conversaciones">
              <Conversaciones />
            </ProtectedRoute>
          }
        />
        <Route
          path="expedientes"
          element={
            <ProtectedRoute requireModulo="expedientes">
              <Expedientes />
            </ProtectedRoute>
          }
        />
        <Route
          path="borradores"
          element={
            <ProtectedRoute requireModulo="borradores">
              <Borradores />
            </ProtectedRoute>
          }
        />
        <Route
          path="doctrina"
          element={
            <ProtectedRoute requireModulo="doctrina">
              <Fuentes />
            </ProtectedRoute>
          }
        />
        <Route
          path="formatos"
          element={
            <ProtectedRoute requireModulo="formatos">
              <Formatos />
            </ProtectedRoute>
          }
        />
        <Route path="perfil" element={<Perfil />} />
      </Route>
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<RootRedirect />} />
    </>,
  ),
);

export function AppRouter(): JSX.Element {
  return (
    <AuthProvider>
      <PermisosProvider>
        <RouterProvider router={router} />
      </PermisosProvider>
    </AuthProvider>
  );
}

// Redirect raíz y catch-all por rol. Sin auth → login.
function RootRedirect() {
  const { isAuthenticated, auth, cargando } = useAuth();
  if (cargando) return null; // restaurando la sesion tras un F5
  if (!isAuthenticated || auth.rol === null) {
    return <Navigate to="/login" replace />;
  }
  if (auth.rol === "administrador") {
    return <Navigate to="/admin" replace />;
  }
  return <Navigate to="/asistente" replace />;
}
