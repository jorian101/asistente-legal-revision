// Test cargos por rol (config/cargos.ts) — Tabla 12 del marco-practico.

import { describe, it, expect } from "vitest";

import { CARGOS_POR_ROL, cargosParaRol } from "../config/cargos";

describe("cargosParaRol (Tabla 12)", () => {
  it("administrador solo tiene Personal Técnico", () => {
    expect(cargosParaRol("administrador")).toEqual(["Personal Técnico"]);
  });

  it("operador_juridico tiene los 4 cargos de la SAC", () => {
    expect(cargosParaRol("operador_juridico")).toEqual([
      "Auditor",
      "Fiscal",
      "Vocal Relator",
      "Secretaria de Cámara",
    ]);
  });

  it("supervisor tiene Vocal Presidente y Auxiliar", () => {
    expect(cargosParaRol("supervisor")).toEqual([
      "Vocal Presidente",
      "Auxiliar de Secretaría de Cámara",
    ]);
  });

  it("ningún rol tiene 'Otro'", () => {
    for (const cargos of Object.values(CARGOS_POR_ROL)) {
      expect(cargos).not.toContain("Otro");
    }
  });

  it("rol null/desconocido devuelve lista vacía", () => {
    expect(cargosParaRol(null)).toEqual([]);
    expect(cargosParaRol("rol-inventado")).toEqual([]);
  });
});
