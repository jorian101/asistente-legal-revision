// Test: el access token vive solo en memoria; sessionStorage guarda el perfil (F-22).
//
// Regla 2: "JWT access en memoria". Persistirlo en sessionStorage lo dejaba en
// claro, legible por cualquier XSS. Ahora solo se guarda el perfil (rol, carnet,
// nombre, id) y al recargar se restaura la sesion pidiendo /auth/refresh (la
// cookie httpOnly la envia el navegador).

import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockAxiosInstance } = vi.hoisted(() => ({
  mockAxiosInstance: {
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { headers: {} },
  },
}));

vi.mock("axios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("axios")>();
  return { ...actual, default: { create: vi.fn(() => mockAxiosInstance) } };
});

const CLAVE = "asistente-legal-auth";
const PERFIL = {
  rol: "operador_juridico",
  carnet: "8012345",
  nombre: "Op",
  id: 7,
};

async function cargarAuth() {
  vi.resetModules();
  return await import("../api/auth");
}

describe("persistencia de la sesion", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("setAuthState guarda solo el perfil, nunca el access token", async () => {
    const auth = await cargarAuth();

    auth.setAuthState({ access_token: "secreto.jwt.token", ...PERFIL });

    expect(auth.getAccessToken()).toBe("secreto.jwt.token"); // en memoria
    const guardado = sessionStorage.getItem(CLAVE) ?? "";
    expect(guardado).not.toContain("secreto");
    expect(JSON.parse(guardado)).toEqual(PERFIL);
  });

  it("un token heredado en sessionStorage se ignora y se borra", async () => {
    sessionStorage.setItem(
      CLAVE,
      JSON.stringify({ access_token: "viejo.jwt.token", ...PERFIL }),
    );

    const auth = await cargarAuth();

    expect(auth.getAccessToken()).toBeNull();
    expect(auth.getAuthState().rol).toBe("operador_juridico");
    expect(sessionStorage.getItem(CLAVE)).not.toContain("viejo");
  });

  it("clearAuthState borra el perfil", async () => {
    const auth = await cargarAuth();
    auth.setAuthState({ access_token: "t", ...PERFIL });

    auth.clearAuthState();

    expect(sessionStorage.getItem(CLAVE)).toBeNull();
    expect(auth.getAuthState().rol).toBeNull();
  });
});
