// Test: refreshAccessToken es un singleton idempotente (Fase 1, bug kick-login).
//
// El bug: axios (interceptor) y fetchWithAuth (consultas/borradores) disparaban
// refresh CONCURRENTES con la misma cookie -> doble rotacion del refresh token
// -> el segundo recibe ReplayError (token ya revocado) -> revocacion total ->
// logout. Ahora ambos comparten la MISMA promesa.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getAccessToken,
  logout,
  refreshAccessToken,
  reintentaEn401,
  setAuthState,
  tokenParaReintento,
} from "../api/auth";

// Hoisted: la instancia axios simulada debe existir ANTES del vi.mock.
const { mockAxiosInstance } = vi.hoisted(() => {
  return {
    mockAxiosInstance: {
      post: vi.fn(),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: { headers: {} },
    },
  };
});

vi.mock("axios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("axios")>();
  return {
    ...actual,
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  };
});

describe("refreshAccessToken (singleton)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuthState({
      access_token: "token-viejo",
      rol: "op",
      carnet: "1",
      nombre: null,
      id: 1,
    });
    mockAxiosInstance.post.mockResolvedValue({
      data: { access_token: "token-nuevo" },
    });
  });

  it("dos llamadas concurrentes disparan UN solo POST /auth/refresh", async () => {
    const [a, b] = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
    ]);

    expect(a).toBe("token-nuevo");
    expect(b).toBe("token-nuevo");
    // Solo una rotacion: el refresh token cookie se usa una vez.
    expect(mockAxiosInstance.post).toHaveBeenCalledTimes(1);
    expect(mockAxiosInstance.post).toHaveBeenCalledWith("/auth/refresh");
  });

  it("actualiza authState con el nuevo token (getAccessToken lo refleja)", async () => {
    await refreshAccessToken();
    expect(getAccessToken()).toBe("token-nuevo");
  });

  it("llamadas secuenciales vuelven a refrescar (promesa se resetea)", async () => {
    await refreshAccessToken();
    await refreshAccessToken();
    expect(mockAxiosInstance.post).toHaveBeenCalledTimes(2);
  });
});

describe("refresh entre pestañas y 401 tardío", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuthState({
      access_token: "token-actual",
      rol: "op",
      carnet: "1",
      nombre: null,
      id: 1,
    });
    mockAxiosInstance.post.mockResolvedValue({
      data: { access_token: "token-nuevo" },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("serializa el refresh con Web Locks cuando el navegador lo soporta", async () => {
    const request = vi.fn((_nombre: string, cb: () => Promise<string>) => cb());
    vi.stubGlobal("navigator", { ...navigator, locks: { request } });

    await expect(refreshAccessToken()).resolves.toBe("token-nuevo");
    expect(request).toHaveBeenCalledWith("auth-refresh", expect.any(Function));
  });

  it("un 401 con un token ya rotado reintenta con el actual sin refrescar", async () => {
    await expect(tokenParaReintento("token-viejo")).resolves.toBe(
      "token-actual",
    );
    expect(mockAxiosInstance.post).not.toHaveBeenCalled();
  });

  it("un 401 con el token vigente sí refresca", async () => {
    await expect(tokenParaReintento("token-actual")).resolves.toBe(
      "token-nuevo",
    );
    expect(mockAxiosInstance.post).toHaveBeenCalledWith("/auth/refresh");
  });

  it("/auth/me y /auth/permisos refrescan; login, refresh y 2FA no", () => {
    expect(reintentaEn401("/auth/permisos")).toBe(true);
    expect(reintentaEn401("/auth/me")).toBe(true);
    expect(reintentaEn401("/auth/login")).toBe(false);
    expect(reintentaEn401("/auth/refresh")).toBe(false);
    expect(reintentaEn401("/auth/verificar-2fa")).toBe(false);
  });

  it("logout con la red caída no relanza y limpia la sesión local", async () => {
    mockAxiosInstance.post.mockRejectedValueOnce(new Error("Network Error"));

    await expect(logout()).resolves.toBeUndefined();
    expect(getAccessToken()).toBeNull();
  });
});
