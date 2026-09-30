// Test Mis Borradores: cards de borradores con autor, acciones Ver el chat /
// Ver borrador final, y publicar desde el detalle.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, describe, it, expect } from "vitest";

import MisBorradores from "../pages/consultas/Borradores";
import { ToastContainer } from "../lib/toasts";
import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { permisosDeTest } from "./helpers";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";

vi.mock("../api/borradores", () => ({
  listarMisBorradores: vi.fn(),
  publicarBorrador: vi.fn(),
  exportarBorrador: vi.fn(),
  actualizarBorrador: vi.fn(),
  obtenerContextoExport: vi.fn().mockResolvedValue({
    tamano_hoja: "carta",
    margenes: { top: 25, right: 20, bottom: 20, left: 40 },
    font: "Arial",
    size_pt: 12,
  }),
  TIPO_BORRADOR_LABEL: {
    dictamen_radicatoria: "Dictamen de radicatoria",
    proyecto_auto_vista_consulta: "Auto de vista — consulta",
    proyecto_auto_vista_apelacion: "Auto de vista — apelación incidental",
    sugerencia_argumentacion: "Sugerencia de argumentación",
  },
}));

vi.mock("../lib/chatStore", () => ({
  chatStore: {
    listarConversaciones: vi.fn().mockReturnValue([]),
  },
}));

import { listarMisBorradores, publicarBorrador } from "../api/borradores";

// Permisos del render; un test puede denegar operaciones antes de renderizar.
let permisos = permisosDeTest();

const mockedListar = listarMisBorradores as ReturnType<typeof vi.fn>;
const mockedPublicar = publicarBorrador as ReturnType<typeof vi.fn>;

const BORRADORES = [
  {
    id: 1,
    expediente_id: 3,
    propietario_id: 7,
    tipo: "proyecto_auto_vista_consulta",
    contenido: "AUTO DE VISTA: se confirma la sentencia impugnada...",
    estado: "borrador",
    plantilla_usada: "proyecto_auto_vista_consulta.md",
    chat_id: 55,
    mensaje_id: 101,
    autor_nombre: "Juan Pérez",
    autor_cargo: "Vocal Relator",
    created_at: "2026-08-15T10:00:00Z",
    updated_at: "2026-08-15T10:00:00Z",
    layout: null,
  },
  {
    id: 2,
    expediente_id: 3,
    propietario_id: 8,
    tipo: "dictamen_radicatoria",
    contenido: "DICTAMEN: la radicatoria es procedente...",
    estado: "publicado",
    plantilla_usada: "dictamen_radicatoria.md",
    chat_id: null,
    mensaje_id: null,
    autor_nombre: "María López",
    autor_cargo: "Auditor",
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:00:00Z",
    layout: null,
  },
];

function renderMisBorradores() {
  const value: AuthState = {
    access_token: "test-token",
    rol: "operador_juridico",
    carnet: "8012345",
    nombre: "Operador Prueba",
    id: 7,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <PermisosContext.Provider value={permisos}>
        <MemoryRouter>
          <MisBorradores />
          <ToastContainer />
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
}

beforeEach(() => {
  permisos = permisosDeTest();
  vi.clearAllMocks();
  mockedListar.mockReset();
  mockedPublicar.mockReset();
  mockedListar.mockResolvedValue(BORRADORES);
  mockedPublicar.mockResolvedValue({ borrador_id: 1, estado: "publicado" });
});

describe("Mis Borradores", () => {
  it("muestra las cards de borradores con autor", async () => {
    renderMisBorradores();
    expect(
      await screen.findByText("Auto de vista — consulta"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Juan Pérez · Vocal Relator/)).toBeInTheDocument();
    expect(screen.getByText(/María López · Auditor/)).toBeInTheDocument();
    expect(screen.getByText("Publicado")).toBeInTheDocument();
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });

  it("sin borradores.eliminar no muestra Eliminar en las cards", async () => {
    permisos = permisosDeTest(["borradores.eliminar"]);
    renderMisBorradores();
    await screen.findByText("Auto de vista — consulta");
    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
  });

  it("abre el detalle con Ver obrado final y publica", async () => {
    const user = userEvent.setup();
    renderMisBorradores();
    await screen.findByText("Auto de vista — consulta");

    await user.click(
      screen.getAllByRole("button", { name: "Ver obrado final" })[0],
    );
    // El detalle es un modal dialog.
    expect(
      await screen.findByRole("dialog", { name: "Detalle del borrador" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/se confirma la sentencia/).length,
    ).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Publicar" }));
    await waitFor(() => {
      expect(mockedPublicar).toHaveBeenCalledWith(1);
    });
  });

  it("muestra Ver el chat para borradores con chat vinculado", async () => {
    renderMisBorradores();
    await screen.findByText("Auto de vista — consulta");
    expect(screen.getAllByRole("button", { name: "Ver el chat" }).length).toBe(
      2,
    );
  });

  it("muestra estado vacío cuando no hay borradores", async () => {
    mockedListar.mockResolvedValue([]);
    renderMisBorradores();
    expect(
      await screen.findByText(/Todavía no guardaste obrados/),
    ).toBeInTheDocument();
  });
});

describe("Mis Borradores: cambios sin guardar", () => {
  // jsdom no trae ResizeObserver y la barra flotante lo usa al seleccionar un bloque.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  // TipTap mide rangos al abrir el editor y jsdom no implementa estas funciones en Range.
  Range.prototype.getClientRects ??= () =>
    ({
      length: 0,
      item: () => null,
      [Symbol.iterator]: [][Symbol.iterator],
    }) as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect ??= () => new DOMRect();

  async function abrirYEditar() {
    renderMisBorradores();
    const botones = await screen.findAllByRole("button", {
      name: /Ver obrado final/,
    });
    await userEvent.click(botones[0]);
    const detalle = await screen.findByRole("dialog", {
      name: "Detalle del borrador",
    });
    await userEvent.click(
      await within(detalle).findByText(/se confirma la sentencia impugnada/),
    );
    await userEvent.click(await screen.findByTitle("Negrita")); // cambio pendiente
  }

  it("Cerrar con cambios pide confirmación y no descarta sin avisar", async () => {
    await abrirYEditar();
    await userEvent.click(screen.getByRole("button", { name: "Cerrar" }));

    expect(await screen.findByText("Descartar cambios")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Seguir editando" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Detalle del borrador" }),
    ).toBeInTheDocument();
  });

  it("Deshacer va de a un paso y Rehacer lo recupera", async () => {
    await abrirYEditar(); // paso 1: negrita
    await userEvent.click(screen.getByTitle("Subrayado")); // paso 2
    // El del pie del detalle (la barra de la hoja tiene otro que solo aparece con cambios).
    const guardar = screen
      .getAllByRole("button", { name: "Guardar todo" })
      .at(-1)!;

    await userEvent.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(guardar).toBeEnabled(); // queda la negrita: antes se descartaba todo

    await userEvent.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(guardar).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Rehacer" }));
    expect(guardar).toBeEnabled();
  });

  it("un obrado publicado se muestra en solo lectura (sin herramientas de edición)", async () => {
    renderMisBorradores();
    const botones = await screen.findAllByRole("button", {
      name: /Ver obrado final/,
    });
    await userEvent.click(botones[1]); // el publicado
    const detalle = await screen.findByRole("dialog", {
      name: "Detalle del borrador",
    });
    await userEvent.click(
      await within(detalle).findByText(/la radicatoria es procedente/),
    );

    expect(within(detalle).queryByTitle("Negrita")).toBeNull(); // sin barra flotante
    expect(
      within(detalle).queryByRole("button", { name: "Guardar todo" }),
    ).toBeNull();
  });

  it("Publicar queda deshabilitado hasta guardar los cambios", async () => {
    await abrirYEditar();
    const publicar = screen.getByRole("button", { name: "Publicar" });
    expect(publicar).toBeDisabled();
    expect(publicar).toHaveAttribute(
      "title",
      "Guarde los cambios antes de continuar",
    );
    expect(mockedPublicar).not.toHaveBeenCalled();
  });
});
