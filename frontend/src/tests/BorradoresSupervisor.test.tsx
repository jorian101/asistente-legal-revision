// Test: flujo del supervisor sobre borradores (F-07).
//
// - En 'pendiente_oficial' el supervisor puede corregir el contenido (editor activo).
// - Un 'oficial' no se edita: el supervisor lo desoficializa a 'pendiente_oficial'
//   ("Volver a solicitud de oficializacion"), corrige y lo vuelve a oficializar.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "../api/auth";
import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { permisosDeTest } from "./helpers";
import { ToastContainer } from "../lib/toasts";
import MisBorradores from "../pages/consultas/Borradores";

vi.mock("../api/borradores", () => ({
  listarMisBorradores: vi.fn(),
  desoficializarBorrador: vi.fn(),
  publicarBorrador: vi.fn(),
  exportarBorrador: vi.fn(),
  actualizarBorrador: vi.fn(),
  obtenerContextoExport: vi.fn().mockResolvedValue({
    tamano_hoja: "carta",
    margenes: { top: 25, right: 20, bottom: 20, left: 40 },
    font: "Arial",
    size_pt: 12,
  }),
  TIPO_BORRADOR_LABEL: { dictamen_radicatoria: "Dictamen de radicatoria" },
}));

vi.mock("../lib/chatStore", () => ({
  chatStore: { listarConversaciones: vi.fn().mockReturnValue([]) },
}));

import { desoficializarBorrador, listarMisBorradores } from "../api/borradores";

// Permisos del render; un test puede denegar operaciones antes de renderizar.
let permisos = permisosDeTest();

const mockedListar = listarMisBorradores as ReturnType<typeof vi.fn>;
const mockedDesoficializar = desoficializarBorrador as ReturnType<typeof vi.fn>;

function borrador(estado: string) {
  return {
    id: 5,
    expediente_id: 3,
    propietario_id: 8, // el operador dueño (no el supervisor)
    tipo: "dictamen_radicatoria",
    contenido: "DICTAMEN: texto a revisar",
    estado,
    plantilla_usada: "dictamen_radicatoria.md",
    chat_id: null,
    mensaje_id: null,
    autor_nombre: "María López",
    autor_cargo: "Auditor",
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:00:00Z",
    layout: null,
  };
}

async function abrirDetalle(
  rol: "supervisor" | "operador_juridico",
  estado: string,
) {
  mockedListar.mockResolvedValue([borrador(estado)]);
  setAuthState({
    access_token: "t",
    rol,
    carnet: "1",
    nombre: "Usuario",
    id: rol === "supervisor" ? 3 : 8,
  });
  const user = userEvent.setup();
  render(
    <AuthProvider>
      <PermisosContext.Provider value={permisos}>
        <MemoryRouter>
          <MisBorradores />
          <ToastContainer />
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
  await user.click(
    await screen.findByRole("button", { name: "Ver obrado final" }),
  );
  await screen.findByRole("dialog", { name: "Detalle del borrador" });
  return user;
}

beforeEach(() => {
  permisos = permisosDeTest();
  vi.clearAllMocks();
  mockedListar.mockReset();
  mockedDesoficializar.mockReset();
});

describe("borradores: supervisor y oficializacion", () => {
  it("el supervisor edita un pendiente_oficial (sin aviso de solo lectura)", async () => {
    await abrirDetalle("supervisor", "pendiente_oficial");

    expect(screen.queryByText(/Vista solo lectura/)).not.toBeInTheDocument();
  });

  it("el operador no edita su borrador ya solicitado como oficial", async () => {
    await abrirDetalle("operador_juridico", "pendiente_oficial");

    expect(screen.getByText(/Vista solo lectura/)).toBeInTheDocument();
  });

  it("un oficial es de solo lectura y el supervisor lo devuelve a solicitud de oficializacion", async () => {
    const user = await abrirDetalle("supervisor", "oficial");
    mockedDesoficializar.mockResolvedValue(borrador("pendiente_oficial"));

    expect(screen.getByText(/Vista solo lectura/)).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: "Volver a solicitud de oficialización",
      }),
    );

    await waitFor(() =>
      expect(mockedDesoficializar).toHaveBeenCalledWith(5, "pendiente_oficial"),
    );
  });

  it("desoficializar pide confirmación antes de llamar al backend", async () => {
    const user = await abrirDetalle("supervisor", "oficial");
    mockedDesoficializar.mockResolvedValue(borrador("publicado"));

    await user.click(screen.getByRole("button", { name: "Desoficializar" }));
    expect(mockedDesoficializar).not.toHaveBeenCalled();

    const dialogo = screen.getByRole("dialog", {
      name: "Desoficializar obrado",
    });
    await user.click(
      within(dialogo).getByRole("button", { name: "Desoficializar" }),
    );
    await waitFor(() =>
      expect(mockedDesoficializar).toHaveBeenCalledWith(5, "publicado"),
    );
  });
});
