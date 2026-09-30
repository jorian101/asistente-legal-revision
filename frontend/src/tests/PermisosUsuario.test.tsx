// Test PermisosUsuario (admin): matriz CRUD por módulo y usuario.
//
// Verifica:
// - Selector de usuario carga sus permisos (override + efectivo).
// - El tri-estado (Default / Permitir / Denegar) muestra el efectivo.
// - Guardar envía los overrides (null = default del rol).
// - Usuario administrador no se puede modificar (selects disabled).

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  Link,
  RouterProvider,
  createMemoryRouter,
  type RouteObject,
} from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import PermisosUsuario from "../pages/admin/PermisosUsuario";
import { ToastContainer } from "../lib/toasts";
import {
  asignarPermisosUsuario,
  listarPermisosUsuario,
  listarUsuarios,
} from "../api/permisos";

vi.mock("../api/permisos", () => ({
  listarPermisosUsuario: vi.fn(),
  asignarPermisosUsuario: vi.fn(),
  listarUsuarios: vi.fn(),
}));

const mockedListarPermisos = listarPermisosUsuario as ReturnType<typeof vi.fn>;
const mockedAsignar = asignarPermisosUsuario as ReturnType<typeof vi.fn>;
const mockedListarUsuarios = listarUsuarios as ReturnType<typeof vi.fn>;

const USUARIOS = [
  {
    id: 1,
    carnet: "op01",
    nombre: "Operador Juridico Fiscal",
    rol: "operador_juridico",
    cargo: "Fiscal",
    activo: true,
  },
  {
    id: 2,
    carnet: "qaadmin",
    nombre: "QA Auditor Admin",
    rol: "administrador",
    cargo: "Otro",
    activo: true,
  },
];

const DETALLE_OPERADOR = [
  {
    clave: "consultar",
    nombre: "Consultar",
    override: {
      puede_crear: null,
      puede_leer: null,
      puede_actualizar: null,
      puede_eliminar: null,
    },
    efectivo: {
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
    default_rol: {
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
  },
  {
    clave: "borradores",
    nombre: "Borradores",
    override: {
      puede_crear: false,
      puede_leer: null,
      puede_actualizar: null,
      puede_eliminar: null,
    },
    efectivo: {
      puede_crear: false,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
    default_rol: {
      puede_crear: true,
      puede_leer: true,
      puede_actualizar: true,
      puede_eliminar: true,
    },
  },
];

// Data router (como en la app): PermisosUsuario usa useBlocker.
function renderPermisos() {
  const rutas: RouteObject[] = [
    {
      path: "/admin/permisos",
      element: (
        <>
          <Link to="/admin/usuarios">Ir a usuarios</Link>
          <PermisosUsuario />
          <ToastContainer />
        </>
      ),
    },
    { path: "/admin/usuarios", element: <div>Página Usuarios</div> },
  ];
  const router = createMemoryRouter(rutas, {
    initialEntries: ["/admin/permisos"],
  });
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedListarUsuarios.mockReset();
  mockedListarPermisos.mockReset();
  mockedAsignar.mockReset();
  mockedListarUsuarios.mockResolvedValue(USUARIOS);
  mockedListarPermisos.mockResolvedValue(DETALLE_OPERADOR);
  mockedAsignar.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
});

// Abre el picker de usuarios (cuando ya cargaron) y elige por carnet.
async function elegirUsuario(
  user: ReturnType<typeof userEvent.setup>,
  carnet: string,
) {
  const trigger = screen.getByRole("button", { name: "Seleccionar usuario" });
  await waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  const dialogo = await screen.findByRole("dialog");
  await user.click(
    within(dialogo).getByRole("button", { name: new RegExp(carnet) }),
  );
}

describe("PermisosUsuario", () => {
  it("muestra la matriz al seleccionar un usuario operador", async () => {
    const user = userEvent.setup();
    renderPermisos();

    await elegirUsuario(user, "op01");

    expect(await screen.findByText("Consultar")).toBeInTheDocument();
    expect(screen.getByText("Borradores")).toBeInTheDocument();
  });

  it("guarda los overrides al tocar una celda y guardar", async () => {
    const user = userEvent.setup();
    renderPermisos();

    await elegirUsuario(user, "op01");
    await screen.findByText("Consultar");

    // En la fila de Consultar, cambiar "leer" a Denegar.
    const fila = screen.getByText("Consultar").closest("tr") as HTMLElement;
    const selectLeer = within(fila).getByLabelText("leer de Consultar");
    await user.selectOptions(selectLeer, "false");

    await user.click(screen.getByRole("button", { name: "Guardar permisos" }));

    await waitFor(() => {
      expect(mockedAsignar).toHaveBeenCalledWith("op01", {
        consultar: expect.objectContaining({ puede_leer: false }),
        borradores: expect.objectContaining({ puede_crear: false }),
      });
    });
  });

  it("pide confirmar antes de descartar cambios al cambiar de usuario", async () => {
    const user = userEvent.setup();
    renderPermisos();

    await elegirUsuario(user, "op01");
    await screen.findByText("Consultar");
    const fila = screen.getByText("Consultar").closest("tr") as HTMLElement;
    await user.selectOptions(
      within(fila).getByLabelText("leer de Consultar"),
      "false",
    );

    await user.click(screen.getByRole("button", { name: /op01/ }));
    const picker = await screen.findByRole("dialog");
    await user.click(within(picker).getByRole("button", { name: /qaadmin/ }));

    await user.click(
      await screen.findByRole("button", { name: "Seguir editando" }),
    );
    expect(mockedListarPermisos).not.toHaveBeenCalledWith("qaadmin");
    expect(
      screen.getByRole("button", { name: "Guardar permisos" }),
    ).toBeEnabled();
  });

  it("pide confirmar antes de navegar a otra sección con cambios sin guardar", async () => {
    const user = userEvent.setup();
    renderPermisos();

    await elegirUsuario(user, "op01");
    await screen.findByText("Consultar");
    const fila = screen.getByText("Consultar").closest("tr") as HTMLElement;
    await user.selectOptions(
      within(fila).getByLabelText("leer de Consultar"),
      "false",
    );

    await user.click(screen.getByRole("link", { name: "Ir a usuarios" }));
    await user.click(
      await screen.findByRole("button", { name: "Seguir editando" }),
    );
    expect(screen.queryByText("Página Usuarios")).toBeNull();

    await user.click(screen.getByRole("link", { name: "Ir a usuarios" }));
    await user.click(
      await screen.findByRole("button", { name: "Descartar y salir" }),
    );
    expect(await screen.findByText("Página Usuarios")).toBeInTheDocument();
  });

  it("sin cambios navega sin preguntar", async () => {
    const user = userEvent.setup();
    renderPermisos();
    await screen.findByRole("button", { name: "Seleccionar usuario" });

    await user.click(screen.getByRole("link", { name: "Ir a usuarios" }));
    expect(await screen.findByText("Página Usuarios")).toBeInTheDocument();
  });

  it("deshabilita la edición para un usuario administrador", async () => {
    const user = userEvent.setup();
    renderPermisos();

    await elegirUsuario(user, "qaadmin");
    await screen.findByText(/no se pueden modificar/);

    expect(
      screen.queryByRole("button", { name: "Guardar permisos" }),
    ).not.toBeInTheDocument();
  });
});
