// Test catálogos derivados del vault (config/catalogos.ts).
//
// Verifica que los catálogos tienen valores únicos y labels legibles, y que
// el helper obtenerLabel cae al valor cuando no hay match (anti-alucinación).

import { describe, it, expect } from "vitest";

import {
  GRADO_MILITAR,
  RESULTADO_AUTO_VISTA,
  SENTIDO_SENTENCIA,
  TIPO_DELITO,
  TIPO_PROCESO,
  TRIBUNAL_ORIGEN,
  obtenerLabel,
} from "../config/catalogos";

const CATALOGOS = [
  TIPO_DELITO,
  GRADO_MILITAR,
  TRIBUNAL_ORIGEN,
  TIPO_PROCESO,
  RESULTADO_AUTO_VISTA,
  SENTIDO_SENTENCIA,
];

describe("catálogos del vault", () => {
  it("todos los catálogos tienen valores únicos", () => {
    for (const catalogo of CATALOGOS) {
      const valores = catalogo.map((c) => c.valor);
      expect(new Set(valores).size).toBe(valores.length);
    }
  });

  it("todos los catálogos tienen labels no vacíos", () => {
    for (const catalogo of CATALOGOS) {
      for (const opcion of catalogo) {
        expect(opcion.label.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("tipo delito incluye los delitos más frecuentes del vault", () => {
    const valores = TIPO_DELITO.map((d) => d.valor);
    expect(valores).toContain("desercion");
    expect(valores).toContain("hurto");
    expect(valores).toContain("homicidio");
    expect(valores).toContain("robo");
  });

  it("tipo proceso incluye apelacion_restringida (gap del vault)", () => {
    expect(TIPO_PROCESO.map((t) => t.valor)).toContain("apelacion_restringida");
  });

  it("obtenerLabel devuelve el label conocido", () => {
    expect(obtenerLabel(TIPO_PROCESO, "consulta")).toBe("Consulta");
  });

  it("obtenerLabel cae al valor si no hay match (anti-alucinación)", () => {
    expect(obtenerLabel(TIPO_DELITO, "DELITO-DESCONOCIDO")).toBe(
      "DELITO-DESCONOCIDO",
    );
  });
});
