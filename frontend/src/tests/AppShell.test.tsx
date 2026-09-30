// AppShell: drawer móvil (☰ + Escape), sidebar colapsable con preferencia
// persistida, menú de usuario con cargo y rol, y búsqueda global Ctrl/Cmd+K
// con grupos según el área.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAuthState } from "../api/auth";
import { AppShell } from "../components/AppShell";
import { chatStore } from "../lib/chatStore";
import type { Modulo } from "../config/modulosPorRol";
import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  logout: vi.fn(),
  clearAuthState: vi.fn(),
  getAuthState: vi.fn(),
  setAuthState: vi.fn(),
  onAuthChange: () => () => {},
  getAccessToken: vi.fn(),
}));

vi.mock("../api/fuentes", () => ({
  CATEGORIA_LABEL: { norma: "Normas" },
  listarFuentes: vi.fn().mockResolvedValue([]),
}));

const MODULOS: Modulo[] = [
  { to: "/asistente/expedientes", label: "Expedientes", descripcion: "" },
  { to: "/asistente/conversaciones", label: "Conversaciones", descripcion: "" },
];

function renderShell(ruta = "/asistente", raiz = "/asistente") {
  (getAuthState as ReturnType<typeof vi.fn>).mockReturnValue({
    access_token: "t",
    rol: "supervisor",
    carnet: "1",
    nombre: "Ana Pérez",
    id: 3,
    cargo: "Vocal Relator",
  });
  return render(
    <AuthProvider>
      <PermisosContext.Provider
        value={{ permisos: [], puede: () => true, recargar: async () => {} }}
      >
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route
              path={raiz}
              element={<AppShell modulos={MODULOS} raiz={raiz} />}
            >
              <Route index element={<div>Inicio</div>} />
              <Route path="*" element={<div>Página</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("AppShell drawer móvil", () => {
  it("☰ abre el menú y Escape lo cierra devolviendo el foco", () => {
    renderShell();
    const menu = screen.getByRole("button", {
      name: "Abrir menú de navegación",
    });
    expect(menu).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
  });
});

describe("AppShell sidebar colapsable", () => {
  it("colapsar persiste la preferencia entre montajes", () => {
    const { unmount } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Colapsar menú" }));
    expect(
      screen.getByRole("button", { name: "Expandir menú" }),
    ).toHaveAttribute("aria-expanded", "false");
    unmount();

    renderShell();
    expect(
      screen.getByRole("button", { name: "Expandir menú" }),
    ).toBeInTheDocument();
  });

  it("colapsado, las etiquetas siguen siendo el nombre accesible", () => {
    localStorage.setItem("shell:rail-colapsado", "1");
    renderShell();
    const link = screen.getByRole("link", { name: "Expedientes" });
    fireEvent.mouseEnter(link);
    expect(screen.getByRole("tooltip", { hidden: true })).toHaveTextContent(
      "Expedientes",
    );
  });
});

describe("AppShell TopBar", () => {
  it("muestra la ubicación Área / Módulo", () => {
    renderShell("/asistente/expedientes");
    const ubicacion = screen.getByRole("navigation", { name: "Ubicación" });
    expect(within(ubicacion).getByText("Expedientes")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("el menú de usuario muestra nombre y cargo, y el rol va en un badge", () => {
    renderShell();
    const cuenta = screen.getByRole("button", { name: "Cuenta de Ana Pérez" });
    expect(cuenta).toHaveTextContent("Vocal Relator");
    expect(screen.getByTitle("Rol: Supervisor")).toHaveTextContent(
      "Supervisor",
    );

    fireEvent.click(cuenta);
    expect(
      screen.getByRole("menuitem", { name: /cerrar sesión/i }),
    ).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("Ctrl+K abre la búsqueda global y Escape la cierra", () => {
    renderShell();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    const input = screen.getByRole("combobox");
    expect(input).toHaveFocus();

    fireEvent.change(input, { target: { value: "expe" } });
    expect(screen.getByRole("option", { name: /Expedientes/ })).toBeVisible();

    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("las conversaciones propias solo aparecen en el área del asistente", () => {
    chatStore.crearConversacion(3, "Consulta sobre deserción");

    const { unmount } = renderShell("/admin", "/admin");
    fireEvent.click(screen.getByRole("button", { name: /buscar/i }));
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "deserción" },
    });
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    unmount();

    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /buscar/i }));
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "deserción" },
    });
    expect(
      screen.getByRole("option", { name: /Consulta sobre deserción/ }),
    ).toBeInTheDocument();
  });
});
