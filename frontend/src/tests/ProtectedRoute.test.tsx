// Test ProtectedRoute: multi-rol + redirect por rol + no autenticado.
//
// Ponytail: cubre happy + bloqueo admin en /asistente + rol permitido.
// Sigue el patrón de LoginForm.test.tsx (MemoryRouter + mock api/auth).

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { ProtectedRoute } from "../router/ProtectedRoute";
import { getAuthState as mockedGetAuthState } from "../api/auth";
import {
  PermisosContext,
  type PermisosContextValue,
} from "../context/usePermisos";
import userEvent from "@testing-library/user-event";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  logout: vi.fn(),
  clearAuthState: vi.fn(),
  getAuthState: vi.fn(),
  setAuthState: vi.fn(),
  onAuthChange: () => () => {}, // AuthProvider se suscribe; no-op en tests
  getAccessToken: vi.fn(),
}));

// Marcadores visuales para detectar a dónde redirige el guard.
// Dos fallbacks porque el redirect depende del rol bloqueado:
//   admin bloqueado → /admin, supervisor/operador bloqueado → /asistente.
const PRIVADO = "contenido-privado";
const FALLBACK_ADMIN = "admin";
const FALLBACK_ASISTENTE = "asistente";

function renderWith(
  rol: "administrador" | "supervisor" | "operador_juridico" | null,
  requireRol?:
    | "administrador"
    | "supervisor"
    | "operador_juridico"
    | Array<"administrador" | "supervisor" | "operador_juridico">,
) {
  (mockedGetAuthState as ReturnType<typeof vi.fn>).mockReturnValue(
    rol === null
      ? { access_token: null, rol: null, carnet: null }
      : { access_token: "token-1", rol, carnet: "8012345" },
  );

  const props = requireRol !== undefined ? { requireRol } : {};

  return render(
    <MemoryRouter initialEntries={["/privado"]}>
      <AuthProvider>
        <Routes>
          <Route
            path="/privado"
            element={
              <ProtectedRoute
                {...(props as {
                  requireRol?:
                    | "administrador"
                    | "supervisor"
                    | "operador_juridico"
                    | Array<
                        "administrador" | "supervisor" | "operador_juridico"
                      >;
                })}
              >
                <div>{PRIVADO}</div>
              </ProtectedRoute>
            }
          />
          <Route path="/admin" element={<div>{FALLBACK_ADMIN}</div>} />
          <Route path="/asistente" element={<div>{FALLBACK_ASISTENTE}</div>} />
          <Route path="/login" element={<div>login</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProtectedRoute", () => {
  it("sin auth redirige a /login", async () => {
    await renderWith(null);
    expect(screen.queryByText(PRIVADO)).not.toBeInTheDocument();
    expect(screen.getByText("login")).toBeInTheDocument();
  });

  it("rol unico permitido pasa el guard", async () => {
    await renderWith("administrador", "administrador");
    expect(screen.getByText(PRIVADO)).toBeInTheDocument();
  });

  it("rol unico no permitido redirige a /asistente", async () => {
    await renderWith("supervisor", "administrador");
    expect(screen.queryByText(PRIVADO)).not.toBeInTheDocument();
    expect(screen.getByText(FALLBACK_ASISTENTE)).toBeInTheDocument();
  });

  it("array de roles: supervisor permitido", async () => {
    await renderWith("supervisor", ["supervisor", "operador_juridico"]);
    expect(screen.getByText(PRIVADO)).toBeInTheDocument();
  });

  it("array de roles: operador_juridico permitido", async () => {
    await renderWith("operador_juridico", ["supervisor", "operador_juridico"]);
    expect(screen.getByText(PRIVADO)).toBeInTheDocument();
  });

  it("array de roles: admin bloqueado de ruta asistente", async () => {
    await renderWith("administrador", ["supervisor", "operador_juridico"]);
    expect(screen.queryByText(PRIVADO)).not.toBeInTheDocument();
    expect(screen.getByText(FALLBACK_ADMIN)).toBeInTheDocument();
  });

  it("sin requireRol: cualquier autenticado pasa", async () => {
    await renderWith("administrador");
    expect(screen.getByText(PRIVADO)).toBeInTheDocument();
  });
});

// --- requireModulo: carga, error con reintento y redirect sin permiso ---

function renderModulo(value: PermisosContextValue) {
  (mockedGetAuthState as ReturnType<typeof vi.fn>).mockReturnValue({
    access_token: "token-1",
    rol: "operador_juridico",
    carnet: "8012345",
  });
  return render(
    <MemoryRouter initialEntries={["/privado"]}>
      <AuthProvider>
        <PermisosContext.Provider value={value}>
          <Routes>
            <Route
              path="/privado"
              element={
                <ProtectedRoute requireModulo="borradores">
                  <div>{PRIVADO}</div>
                </ProtectedRoute>
              }
            />
            <Route
              path="/asistente"
              element={<div>{FALLBACK_ASISTENTE}</div>}
            />
          </Routes>
        </PermisosContext.Provider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const base = { recargar: vi.fn(async () => {}) };

describe("ProtectedRoute con requireModulo", () => {
  it("muestra carga mientras llegan los permisos (no pantalla en blanco)", () => {
    renderModulo({ ...base, permisos: null, puede: () => false });
    expect(screen.getByRole("status")).toHaveTextContent(/Cargando permisos/);
  });

  it("si los permisos fallan, ofrece reintentar", async () => {
    const recargar = vi.fn(async () => {});
    renderModulo({ permisos: null, error: true, puede: () => false, recargar });
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(recargar).toHaveBeenCalled();
  });

  it("sin permiso de leer el módulo redirige a la raíz del área", () => {
    renderModulo({ ...base, permisos: [], puede: () => false });
    expect(screen.queryByText(PRIVADO)).not.toBeInTheDocument();
    expect(screen.getByText(FALLBACK_ASISTENTE)).toBeInTheDocument();
  });

  it("con permiso de leer muestra el contenido", () => {
    renderModulo({ ...base, permisos: [], puede: () => true });
    expect(screen.getByText(PRIVADO)).toBeInTheDocument();
  });
});
