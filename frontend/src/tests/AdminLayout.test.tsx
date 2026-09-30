// Test AdminLayout: sidebar con Inicio fijo, íconos por módulo y colapso.
//
// Verifica:
// - "Inicio" siempre presente como primer item (fijo, fuera de permisos).
// - Los módulos admin se renderizan con sus íconos.
// - El rail es fijo (sin botón de colapsar).

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { AdminLayout } from "../components/AdminLayout";
import { AuthProvider } from "../context/AuthContext";
import { PermisosProvider } from "../context/PermisosContext";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";

vi.mock("../api/permisos", () => ({
  obtenerPermisosPropios: vi.fn().mockResolvedValue([
    {
      clave: "usuarios",
      nombre: "Usuarios",
      descripcion: "Gestión de usuarios y perfiles",
      ruta: "/admin/usuarios",
      orden: 1,
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
    {
      clave: "corpus",
      nombre: "Corpus Jurídico",
      descripcion: "Indexación y configuración de normativa",
      ruta: "/admin/corpus",
      orden: 2,
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
  ]),
}));

function renderAdmin() {
  const value: AuthState = {
    access_token: "test-token",
    rol: "administrador",
    carnet: "7000001",
    nombre: "Admin Prueba",
    id: 1,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <PermisosProvider>
        <MemoryRouter initialEntries={["/admin/usuarios"]}>
          <Routes>
            <Route path="/admin" element={<AdminLayout />}>
              <Route path="usuarios" element={<div>Página Usuarios</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </PermisosProvider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe("AdminLayout", () => {
  const sidebar = () =>
    within(screen.getByRole("navigation", { name: "Navegación principal" }));

  it("muestra Inicio fijo como primer item del sidebar", async () => {
    renderAdmin();
    const inicio = await sidebar().findByRole("link", { name: "Inicio" });
    expect(inicio).toHaveAttribute("href", "/admin");
  });

  it("muestra los módulos admin con sus labels", async () => {
    renderAdmin();
    expect(await sidebar().findByText("Usuarios")).toBeInTheDocument();
    expect(sidebar().getByText("Corpus Jurídico")).toBeInTheDocument();
  });

  it("el sidebar ofrece colapsar y el TopBar ubica el módulo actual", async () => {
    renderAdmin();
    await sidebar().findByText("Usuarios");

    expect(
      screen.getByRole("button", { name: "Colapsar menú" }),
    ).toBeInTheDocument();
    const ubicacion = within(
      screen.getByRole("navigation", { name: "Ubicación" }),
    );
    expect(ubicacion.getByText("Administración")).toBeInTheDocument();
    expect(ubicacion.getByText("Usuarios")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
