// Test Modulos (admin): catálogo de módulos con edición inline y toggle activo.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import Modulos from "../pages/admin/Modulos";
import { ToastContainer } from "../lib/toasts";

vi.mock("../api/permisos", () => ({
  listarModulos: vi.fn(),
  actualizarModulo: vi.fn(),
}));

import { actualizarModulo, listarModulos } from "../api/permisos";

const mockedListar = listarModulos as ReturnType<typeof vi.fn>;
const mockedActualizar = actualizarModulo as ReturnType<typeof vi.fn>;

const MODULOS = [
  {
    clave: "usuarios",
    nombre: "Usuarios",
    descripcion: "Gestión de usuarios y perfiles",
    ruta: "/admin/usuarios",
    orden: 1,
    activo: true,
  },
  {
    clave: "chats",
    nombre: "Chats privados",
    descripcion: "Espacios de trabajo por expediente",
    ruta: "/asistente/chats",
    orden: 13,
    activo: false,
  },
];

function renderModulos() {
  return render(
    <MemoryRouter>
      <Modulos />
      <ToastContainer />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedListar.mockReset();
  mockedActualizar.mockReset();
  mockedListar.mockResolvedValue(MODULOS);
  mockedActualizar.mockResolvedValue({ ...MODULOS[0] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Modulos", () => {
  it("carga y muestra el catálogo", async () => {
    renderModulos();
    expect(await screen.findByText("Usuarios")).toBeInTheDocument();
    expect(screen.getByText("Chats privados")).toBeInTheDocument();
    const filaUsuarios = screen
      .getByText("Usuarios")
      .closest("tr") as HTMLElement;
    expect(
      within(filaUsuarios).getByRole("button", { name: "Activo" }),
    ).toBeInTheDocument();
    const filaChats = screen
      .getByText("Chats privados")
      .closest("tr") as HTMLElement;
    expect(
      within(filaChats).getByRole("button", { name: "Inactivo" }),
    ).toBeInTheDocument();
  });

  it("edita el nombre inline y guarda", async () => {
    const user = userEvent.setup();
    renderModulos();
    await screen.findByText("Usuarios");

    const fila = screen.getByText("Usuarios").closest("tr") as HTMLElement;
    const botonEditar = within(fila).getByRole("button", {
      name: "Editar nombre de Usuarios",
    });
    await user.click(botonEditar);

    const input = within(fila).getByRole("textbox", { name: "Editar nombre" });
    await user.clear(input);
    await user.type(input, "Usuarios v2");
    await user.click(within(fila).getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mockedActualizar).toHaveBeenCalledWith("usuarios", {
        nombre: "Usuarios v2",
      });
    });
  });

  it("alterna activo con el toggle tras confirmar", async () => {
    const user = userEvent.setup();
    renderModulos();
    await screen.findByText("Usuarios");

    const fila = screen.getByText("Usuarios").closest("tr") as HTMLElement;
    const toggle = within(fila).getByRole("button", { name: "Activo" });

    // Cancelar no cambia nada.
    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(mockedActualizar).not.toHaveBeenCalled();

    await user.click(toggle);
    const dialogo = screen.getByRole("dialog", { name: "Desactivar módulo" });
    await user.click(
      within(dialogo).getByRole("button", { name: "Desactivar" }),
    );

    await waitFor(() => {
      expect(mockedActualizar).toHaveBeenCalledWith("usuarios", {
        activo: false,
      });
    });
  });
});
