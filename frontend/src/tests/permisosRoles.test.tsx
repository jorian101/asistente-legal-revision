// Fase 1 roles: guard por módulo, puede() cerrado sin permisos y remapeo
// de Formatos al área del asistente (supervisor).

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ModuloPermisoDTO } from "../api/permisos";
import { getAuthState } from "../api/auth";
import { AuthProvider } from "../context/AuthContext";
import {
  PermisosContext,
  type PermisosContextValue,
} from "../context/usePermisos";
import {
  modulosDashboardArea,
  modulosDesdePermisos,
} from "../config/modulosPorRol";
import { ProtectedRoute } from "../router/ProtectedRoute";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  logout: vi.fn(),
  clearAuthState: vi.fn(),
  getAuthState: vi.fn(),
  setAuthState: vi.fn(),
  onAuthChange: () => () => {},
  getAccessToken: vi.fn(),
}));

const permiso = (over: Partial<ModuloPermisoDTO>): ModuloPermisoDTO => ({
  clave: "formatos",
  nombre: "Formatos TSJM",
  descripcion: "Layouts",
  ruta: "/admin/formatos",
  orden: 20,
  puede_crear: true,
  puede_leer: true,
  puede_actualizar: true,
  puede_eliminar: false,
  ...over,
});

function renderGuard(permisos: ModuloPermisoDTO[] | null) {
  (getAuthState as ReturnType<typeof vi.fn>).mockReturnValue({
    access_token: "t",
    rol: "supervisor",
    carnet: "1",
  });
  const value: PermisosContextValue = {
    permisos,
    puede: (clave, op) =>
      permisos?.find((m) => m.clave === clave)?.[`puede_${op}`] ?? false,
    recargar: async () => {},
  };
  return render(
    <MemoryRouter initialEntries={["/privado"]}>
      <AuthProvider>
        <PermisosContext.Provider value={value}>
          <Routes>
            <Route
              path="/privado"
              element={
                <ProtectedRoute requireModulo="formatos">
                  <div>contenido</div>
                </ProtectedRoute>
              }
            />
            <Route path="/asistente" element={<div>asistente</div>} />
          </Routes>
        </PermisosContext.Provider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute requireModulo", () => {
  it("deja pasar con permiso de lectura", () => {
    renderGuard([permiso({})]);
    expect(screen.getByText("contenido")).toBeInTheDocument();
  });

  it("redirige si un override quitó la lectura", () => {
    renderGuard([permiso({ puede_leer: false })]);
    expect(screen.getByText("asistente")).toBeInTheDocument();
  });

  it("espera (no muestra contenido) mientras cargan los permisos", () => {
    renderGuard(null);
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
    expect(screen.queryByText("asistente")).not.toBeInTheDocument();
  });
});

describe("Formatos en el área del asistente", () => {
  it("el supervisor ve Formatos en /asistente/formatos", () => {
    const m = modulosDesdePermisos([permiso({})], "asistente");
    expect(m[0]?.to).toBe("/asistente/formatos");
    expect(modulosDashboardArea([permiso({})], "asistente")).toHaveLength(1);
  });

  it("el admin conserva /admin/formatos", () => {
    const m = modulosDashboardArea([permiso({})], "admin");
    expect(m[0]?.to).toBe("/admin/formatos");
  });
});
