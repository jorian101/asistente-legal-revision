import { describe, expect, it } from "vitest";

import { FUENTE_BASE, fuenteCss, normalizarFuente } from "./fuentes";

describe("normalizarFuente", () => {
  it.each([
    ["ArialMT", "Arial"],
    ["Arial-BoldMT", "Arial"],
    ["Arial-ItalicMT", "Arial"],
    ["Arial-BoldItalicMT", "Arial"],
    ["ABCDEF+Arial", "Arial"],
    ["TimesNewRomanPSMT", "Times New Roman"],
    ["ArialNarrow", "Arial Narrow"],
    ["Arial", "Arial"],
    ["Times New Roman", "Times New Roman"],
  ])("%s -> %s", (entrada, esperado) => {
    expect(normalizarFuente(entrada)).toBe(esperado);
  });

  it("sin fuente devuelve null", () => {
    expect(normalizarFuente(null)).toBeNull();
    expect(normalizarFuente("")).toBeNull();
  });
});

describe("fuenteCss", () => {
  it("el respaldo es Arial, nunca serif", () => {
    expect(fuenteCss("ArialMT")).toBe(`"Arial", ${FUENTE_BASE}`);
    expect(fuenteCss(null)).toBe(FUENTE_BASE);
    expect(fuenteCss("Batang")).not.toContain("serif,");
    expect(FUENTE_BASE.startsWith("Arial")).toBe(true);
  });
});
