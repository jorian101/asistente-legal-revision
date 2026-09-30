// Test LoginForm: render + submit exitoso + error 401.
//
// Ponytail: mínimo check que cubre happy + error path sin montar
// el árbol completo del router. Usa un mock del módulo api/auth
// para evitar network.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { LoginForm } from "../components/LoginForm";
import { useAuth } from "../context/useAuth";
import { ToastContainer } from "../lib/toasts";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  verificar2Fa: vi.fn(),
  logout: vi.fn(),
  clearAuthState: vi.fn(),
  getAuthState: () => ({
    access_token: null,
    rol: null,
    carnet: null,
    nombre: null,
    id: null,
  }),
  setAuthState: vi.fn(),
  onAuthChange: () => () => {}, // AuthProvider se suscribe; no-op en tests
  getAccessToken: () => null,
}));

import {
  login as mockedLogin,
  verificar2Fa as mockedVerificar2Fa,
} from "../api/auth";

function renderLoginForm() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginForm />
        <AuthProbe />
        <ToastContainer />
      </AuthProvider>
    </MemoryRouter>,
  );
}

// Probe: expone el estado de auth del context para verificar que el 2FA
// sincroniza React (bug: verificar2Fa actualizaba solo sessionStorage/module
// state y ProtectedRoute rebotaba a /login).
function AuthProbe() {
  const { isAuthenticated, auth } = useAuth();
  return (
    <div data-testid="auth-probe">
      {isAuthenticated ? `autenticado:${auth.rol}` : "no-auth"}
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LoginForm", () => {
  it("rendera carnet + password + submit", () => {
    renderLoginForm();
    expect(screen.getByLabelText(/carnet/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ingresar/i })).toBeEnabled();
  });

  it("login exitoso llama a api.login con carnet+password", async () => {
    const user = userEvent.setup();
    mockLoginResolved({
      access_token: "token-1",
      rol: "administrador",
      carnet: "8012345",
    });

    renderLoginForm();

    await user.type(screen.getByLabelText(/carnet/i), "8012345");
    await user.type(screen.getByLabelText(/contraseña/i), "s3cret!");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(mockedLogin).toHaveBeenCalledWith("8012345", "s3cret!");
    });
  });

  it("muestra toast error 401 como credenciales invalidas", async () => {
    const user = userEvent.setup();
    mockLoginRejected({ status: 401 });

    renderLoginForm();

    await user.type(screen.getByLabelText(/carnet/i), "8012345");
    await user.type(screen.getByLabelText(/contraseña/i), "wrong");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByText(/credenciales inválidas/i)).toBeInTheDocument();
    });
  });

  it("muestra toast cuenta bloqueada para 423", async () => {
    const user = userEvent.setup();
    mockLoginRejected({ status: 423 });

    renderLoginForm();

    await user.type(screen.getByLabelText(/carnet/i), "8012345");
    await user.type(screen.getByLabelText(/contraseña/i), "wrong");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByText(/cuenta bloqueada/i)).toBeInTheDocument();
    });
  });

  it("requiere 2FA: tras login pide codigo y verificar2Fa emite tokens", async () => {
    const user = userEvent.setup();
    mockLoginResolved({ requiere_2fa: true, carnet: "8012345" });
    (mockedVerificar2Fa as ReturnType<typeof vi.fn>).mockResolvedValue({
      access_token: "token-2fa",
      rol: "operador_juridico",
      carnet: "8012345",
      id: 7,
    });

    renderLoginForm();

    await user.type(screen.getByLabelText(/carnet/i), "8012345");
    await user.type(screen.getByLabelText(/contraseña/i), "s3cret!");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    // Paso 2: input de codigo visible
    expect(
      await screen.findByLabelText(/código de verificación/i),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText(/código de verificación/i), "123456");
    await user.click(screen.getByRole("button", { name: /verificar código/i }));

    await waitFor(() => {
      expect(mockedVerificar2Fa).toHaveBeenCalledWith("8012345", "123456");
    });

    // El 2FA sincroniza el estado React del AuthContext (fix: rebote a /login).
    await waitFor(() => {
      expect(screen.getByTestId("auth-probe")).toHaveTextContent(
        "autenticado:operador_juridico",
      );
    });
  });
});

function mockLoginResolved(resp: {
  access_token?: string;
  requiere_2fa?: boolean;
  rol?: string;
  carnet: string;
}) {
  (mockedLogin as ReturnType<typeof vi.fn>).mockResolvedValue(resp);
}

function mockLoginRejected({ status }: { status: number }) {
  const err: { response: { status: number; data?: { detail?: string } } } = {
    response: { status },
  };
  (mockedLogin as ReturnType<typeof vi.fn>).mockRejectedValue(err);
}
