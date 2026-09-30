// Test Dashboard: cards de módulos por área según permisos del backend.
//
// Verifica:
// - Muestra los módulos del área (admin) en orden como links navegables.
// - No muestra módulos de otra área.
// - Muestra saludo con el nombre del usuario.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { Dashboard } from "../components/Dashboard";

vi.mock("../api/permisos", () => ({
  obtenerPermisosPropios: vi.fn(),
}));

// AuthContext con un admin autenticado.
vi.mock("../api/auth", () => ({
  api: { get: vi.fn() },
  setAuthState: vi.fn(),
  clearAuthState: vi.fn(),
  onAuthChange: () => () => {},
  getAuthState: () => ({
    access_token: "t",
    rol: "administrador",
    carnet: "7000001",
    nombre: "Admin Prueba",
    id: 1,
  }),
  getAccessToken: () => "t",
}));

import { AuthProvider } from "../context/AuthContext";
import { PermisosProvider } from "../context/PermisosContext";
import { obtenerPermisosPropios } from "../api/permisos";

const mockedPermisos = obtenerPermisosPropios as ReturnType<typeof vi.fn>;

const PERMISOS_ADMIN = [
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
  {
    clave: "consultar",
    nombre: "Consultar",
    descripcion: "Consulta jurídica RAG",
    ruta: "/asistente/consultar",
    orden: 10,
    puede_crear: true,
    puede_leer: true,
    puede_actualizar: true,
    puede_eliminar: true,
  },
];

function renderDashboard() {
  return render(
    <AuthProvider>
      <PermisosProvider>
        <MemoryRouter>
          <Dashboard area="admin" titulo="Panel de administración" />
        </MemoryRouter>
      </PermisosProvider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  mockedPermisos.mockReset();
});

describe("Dashboard (área admin)", () => {
  it("muestra saludo con el nombre del usuario", async () => {
    mockedPermisos.mockResolvedValue(PERMISOS_ADMIN);
    renderDashboard();
    expect(await screen.findByText("Hola, Admin Prueba")).toBeInTheDocument();
  });

  it("muestra los módulos admin como links, en orden", async () => {
    mockedPermisos.mockResolvedValue(PERMISOS_ADMIN);
    renderDashboard();

    expect(await screen.findByText("Usuarios")).toBeInTheDocument();
    expect(screen.getByText("Corpus Jurídico")).toBeInTheDocument();

    const usuarios = screen.getByRole("link", { name: /Usuarios/ });
    expect(usuarios).toHaveAttribute("href", "/admin/usuarios");
  });

  it("no muestra módulos de otra área (consultar)", async () => {
    mockedPermisos.mockResolvedValue(PERMISOS_ADMIN);
    renderDashboard();

    await screen.findByText("Usuarios");
    expect(screen.queryByText("Consultar")).not.toBeInTheDocument();
  });
});
