// Test: reintento tras 401 en fetchWithAuth (consultas), sin mutar `options`.
//
// Caracterizacion previa al refactor de F-06: un 401 dispara UN refresh y UN
// reintento; si el reintento tambien da 401 no se reintenta de nuevo; si el
// refresh falla se limpia la sesion.

import { beforeEach, describe, expect, it, vi } from "vitest";

const { refreshMock, clearMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
  clearMock: vi.fn(),
}));

vi.mock("../api/auth", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  getAccessToken: () => "token-viejo",
  // El token usado es el vigente, así que tokenParaReintento refresca.
  tokenParaReintento: refreshMock,
  reintentaEn401: () => true,
  clearAuthState: clearMock,
}));

import { responderConsulta } from "../api/consultas";

const BODY = { consulta: "hola" } as Parameters<typeof responderConsulta>[0];

function respuesta(status: number): Response {
  return new Response("", { status });
}

describe("fetchWithAuth (consultas)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    refreshMock.mockReset();
    clearMock.mockReset();
  });

  it("401 -> un refresh y un unico reintento con el token nuevo", async () => {
    refreshMock.mockResolvedValue("token-nuevo");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(respuesta(401))
      .mockResolvedValueOnce(respuesta(500));

    await expect(responderConsulta(BODY)).rejects.toThrow();

    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const headers = fetchMock.mock.calls[1][1]?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token-nuevo");
  });

  it("si el reintento tambien da 401 no vuelve a refrescar", async () => {
    refreshMock.mockResolvedValue("token-nuevo");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respuesta(401));

    await expect(responderConsulta(BODY)).rejects.toThrow();

    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("si el refresh falla limpia la sesion y lanza Unauthorized", async () => {
    refreshMock.mockRejectedValue(new Error("refresh caido"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(respuesta(401));

    await expect(responderConsulta(BODY)).rejects.toThrow("Unauthorized");

    expect(clearMock).toHaveBeenCalledTimes(1);
  });
});
