// Test del layout del asistente: rail fijo + único toggle (Historial).
//
// El rail de navegación es fijo (sin toggle); el panel de historial del chat
// es opcional y solo existe en /asistente/consultar.

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultaLayout } from "../components/ConsultaLayout";
import Asistente from "../pages/consultas/Asistente";
import { AuthProvider } from "../context/AuthContext";
import { PermisosProvider } from "../context/PermisosContext";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";
import { SidebarProvider } from "../components/chat/ChatSidebarContext";

vi.mock("../api/consultas", () => ({
  responderConsulta: vi.fn(),
}));

// Permisos del operador: expedientes + consultar (sidebar dinámico).
vi.mock("../api/permisos", () => ({
  obtenerPermisosPropios: vi.fn().mockResolvedValue([
    {
      clave: "expedientes",
      nombre: "Expedientes",
      descripcion: "Apertura y gestión de expedientes",
      ruta: "/asistente/expedientes",
      orden: 9,
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
    {
      clave: "doctrina",
      nombre: "Doctrina",
      descripcion: "Doctrina global y aprobaciones",
      ruta: "/asistente/doctrina",
      orden: 14,
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
  ]),
}));

function renderEn(ruta: string) {
  const value: AuthState = {
    access_token: "test-token",
    rol: "operador_juridico",
    carnet: "1001",
    nombre: "Operador de Prueba",
    id: 1,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <PermisosProvider>
        <MemoryRouter initialEntries={[ruta]}>
          <SidebarProvider>
            <Routes>
              <Route path="/asistente" element={<ConsultaLayout />}>
                <Route index element={<div>Inicio</div>} />
                <Route path="consultar" element={<Asistente />} />
              </Route>
            </Routes>
          </SidebarProvider>
        </MemoryRouter>
      </PermisosProvider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe("ConsultaLayout (rail fijo + panel de historial)", () => {
  it("el rail de navegación y el historial conviven en /consultar", () => {
    renderEn("/asistente/consultar");

    expect(
      screen.getByRole("link", { name: /expedientes/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /nueva conversacion/i }),
    ).toBeInTheDocument();
  });

  it("no hay botones de colapsar el rail ni de alternar sidebars", () => {
    renderEn("/asistente/consultar");

    expect(
      screen.queryByRole("button", { name: /alternar sidebar|chat lateral/i }),
    ).not.toBeInTheDocument();
  });

  it("el único toggle (Historial) abre y cierra el panel sin tocar el rail", () => {
    renderEn("/asistente/consultar");

    const toggle = screen.getByRole("button", { name: "Historial" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("button", { name: /nueva conversacion/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /expedientes/i }),
    ).toBeInTheDocument();
  });

  it("fuera de Consultar solo hay rail (sin panel de historial)", () => {
    renderEn("/asistente");

    expect(
      screen.getByRole("link", { name: /expedientes/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Historial" }),
    ).not.toBeInTheDocument();
  });

  it("muestra Doctrina cuando el permiso tiene ruta /asistente/doctrina", async () => {
    renderEn("/asistente");

    expect(
      await screen.findByRole("link", { name: /doctrina/i }),
    ).toBeInTheDocument();
  });
});
