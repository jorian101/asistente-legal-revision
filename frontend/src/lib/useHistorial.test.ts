import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useHistorial } from "./useHistorial";

type O = Record<string, string>;

describe("useHistorial (deshacer/rehacer por pasos)", () => {
  it("deshace de a un paso, no todo", () => {
    const { result } = renderHook(() => useHistorial<O>({}));
    act(() => result.current.cambiar((p) => ({ ...p, a: "1" })));
    act(() => result.current.cambiar((p) => ({ ...p, b: "2" })));
    act(() => result.current.deshacer());
    expect(result.current.estado).toEqual({ a: "1" });
    expect(result.current.puedeDeshacer).toBe(true);
  });

  it("rehace lo deshecho, y un cambio nuevo borra lo rehacible", () => {
    const { result } = renderHook(() => useHistorial<O>({}));
    act(() => result.current.cambiar((p) => ({ ...p, a: "1" })));
    act(() => result.current.deshacer());
    expect(result.current.puedeRehacer).toBe(true);
    act(() => result.current.rehacer());
    expect(result.current.estado).toEqual({ a: "1" });
    act(() => result.current.deshacer());
    act(() => result.current.cambiar((p) => ({ ...p, c: "3" })));
    expect(result.current.puedeRehacer).toBe(false);
  });

  it("lo tipeado seguido en un mismo bloque es un solo paso", () => {
    const { result } = renderHook(() => useHistorial<O>({}));
    act(() => result.current.cambiar((p) => ({ ...p, a: "h" }), "editor:a"));
    act(() => result.current.cambiar((p) => ({ ...p, a: "ho" }), "editor:a"));
    act(() => result.current.cambiar((p) => ({ ...p, a: "hola" }), "editor:a"));
    act(() => result.current.deshacer());
    expect(result.current.estado).toEqual({});
    expect(result.current.puedeDeshacer).toBe(false);
  });

  it("reiniciar limpia el historial (tras guardar o cancelar)", () => {
    const { result } = renderHook(() => useHistorial<O>({}));
    act(() => result.current.cambiar((p) => ({ ...p, a: "1" })));
    act(() => result.current.reiniciar({}));
    expect(result.current.puedeDeshacer).toBe(false);
    expect(result.current.estado).toEqual({});
  });
});
