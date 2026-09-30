// Tests streamResume: pendiente en sessionStorage + poll con backoff.

import { beforeEach, describe, expect, it, vi } from "vitest";

import { obtenerHistorialDetalle } from "../api/consultas";
import {
  esperarRespuestaFinal,
  guardarPendiente,
  leerPendiente,
  limpiarPendiente,
} from "../lib/streamResume";

vi.mock("../api/consultas", () => ({
  obtenerHistorialDetalle: vi.fn(),
}));

const mockedDetalle = obtenerHistorialDetalle as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.useFakeTimers();
});

describe("streamResume", () => {
  it("guarda, lee y limpia el pendiente", () => {
    expect(leerPendiente()).toBeNull();
    guardarPendiente({
      historialId: 42,
      chatId: "c1",
      pregunta: "hola",
      ts: 1,
    });
    expect(leerPendiente()).toEqual({
      historialId: 42,
      chatId: "c1",
      pregunta: "hola",
      ts: 1,
    });
    limpiarPendiente();
    expect(leerPendiente()).toBeNull();
  });

  it("devuelve la respuesta cuando el backend terminó", async () => {
    mockedDetalle.mockResolvedValue({
      id: 42,
      pregunta: "hola",
      respuesta: "texto final",
      estado: "completado",
      tipo_respuesta: "consulta_simple",
      modelo_llm: "m",
    });
    const p = esperarRespuestaFinal(42);
    await vi.runAllTimersAsync();
    await expect(p).resolves.toEqual({ respuesta: "texto final" });
    expect(mockedDetalle).toHaveBeenCalledWith(42);
  });

  it("espera si aún está en progreso y agota intentos con error", async () => {
    mockedDetalle.mockResolvedValue({
      id: 42,
      pregunta: "hola",
      respuesta: null,
      estado: "en_progreso",
      tipo_respuesta: null,
      modelo_llm: null,
    });
    const p = esperarRespuestaFinal(42);
    await vi.runAllTimersAsync();
    const res = await p;
    expect("error" in res).toBe(true);
    expect(mockedDetalle.mock.calls.length).toBeGreaterThan(3);
  });

  it("P1: en_progreso con parcial NO se da por terminado — sigue polleando y llama onParcial", async () => {
    // Regresión: el backend ahora persiste el parcial (throttled) mientras
    // sigue generando, así que `respuesta` truthy con estado en_progreso ya
    // NO significa "terminó" — antes esto cortaba al primer parcial.
    mockedDetalle.mockResolvedValue({
      id: 42,
      pregunta: "hola",
      respuesta: "texto parcial acumulado",
      estado: "en_progreso",
      tipo_respuesta: null,
      modelo_llm: null,
    });
    const parciales: string[] = [];
    const p = esperarRespuestaFinal(42, undefined, (texto) =>
      parciales.push(texto),
    );
    await vi.runAllTimersAsync();
    const res = await p;

    // No resolvió con { respuesta } al primer parcial: agotó intentos (error).
    expect("error" in res).toBe(true);
    expect(mockedDetalle.mock.calls.length).toBeGreaterThan(3);
    // Pero sí reportó el parcial en cada poll mientras esperaba.
    expect(parciales.length).toBeGreaterThan(0);
    expect(parciales.every((t) => t === "texto parcial acumulado")).toBe(true);
  });

  it("estado error del backend termina como error sin agotar", async () => {
    mockedDetalle.mockResolvedValue({
      id: 42,
      pregunta: "hola",
      respuesta: null,
      estado: "error",
      tipo_respuesta: null,
      modelo_llm: null,
    });
    const p = esperarRespuestaFinal(42);
    await vi.runAllTimersAsync();
    await expect(p).resolves.toEqual({
      error: "La consulta terminó con error en el servidor.",
    });
    expect(mockedDetalle).toHaveBeenCalledTimes(1);
  });
});
