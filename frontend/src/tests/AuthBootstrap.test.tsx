// Test: al recargar (F5) con perfil en sessionStorage y sin token, AuthProvider
// restaura la sesion con UN solo POST /auth/refresh y las rutas protegidas
// esperan (no redirigen) mientras tanto (F-22).

import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockAxiosInstance } = vi.hoisted(() => ({
  mockAxiosInstance: {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { headers: {} },
  },
}));

vi.mock("axios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("axios")>();
  return { ...actual, default: { create: vi.fn(() => mockAxiosInstance) } };
});

const CLAVE = "asistente-legal-auth";

async function renderizarApp() {
  vi.resetModules();
  const { AuthProvider } = await import("../context/AuthContext");
  const { ProtectedRoute } = await import("../router/ProtectedRoute");
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={["/privado"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/privado"
              element={
                <ProtectedRoute>
                  <div>contenido-privado</div>
                </ProtectedRoute>
              }
            />
            <Route path="/login" element={<div>pagina-login</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </StrictMode>,
  );
}

describe("arranque de sesion por refresh", () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockAxiosInstance.post.mockReset();
    sessionStorage.setItem(
      CLAVE,
      JSON.stringify({
        rol: "operador_juridico",
        carnet: "8012345",
        nombre: "Op",
        id: 7,
      }),
    );
  });

  it("restaura la sesion con un solo refresh y muestra la ruta", async () => {
    mockAxiosInstance.post.mockResolvedValue({
      data: { access_token: "token-nuevo" },
    });

    await renderizarApp();

    // Mientras se restaura, el guard no redirige a /login.
    expect(screen.queryByText("pagina-login")).not.toBeInTheDocument();
    expect(await screen.findByText("contenido-privado")).toBeInTheDocument();
    expect(mockAxiosInstance.post).toHaveBeenCalledTimes(1);
    expect(mockAxiosInstance.post).toHaveBeenCalledWith("/auth/refresh");
    expect(sessionStorage.getItem(CLAVE)).not.toContain("token-nuevo");
  });

  it("si el refresh falla limpia la sesion y redirige a /login", async () => {
    mockAxiosInstance.post.mockRejectedValue(new Error("401"));

    await renderizarApp();

    expect(await screen.findByText("pagina-login")).toBeInTheDocument();
    await waitFor(() => expect(sessionStorage.getItem(CLAVE)).toBeNull());
  });
});
