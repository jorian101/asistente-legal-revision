// La categoría de una fuente fijada se deduce del prefijo de su abreviatura.

import { describe, expect, it } from "vitest";

import { categoriaDeRef } from "./categoriaRef";

describe("categoriaDeRef", () => {
  it.each([
    ["LIB-ATIENZA-INTERP-2019", "doctrina"],
    ["LIB-DOCTRINA-APELACION-INCIDENTAL", "doctrina"],
    ["SCP-0623-2024-S4", "jurisprudencia"],
    ["SC-1180-2011-R", "jurisprudencia"],
    ["CIDH-TC-PERU-2001", "jurisprudencia"],
    ["JUR-MI-SENTENCIA", "jurisprudencia"],
    ["CPE", "norma"],
    ["CPPM", "norma"],
    ["LEY-LEY-DE-RECURSOS", "norma"],
  ])("%s es %s", (ref, esperada) => {
    expect(categoriaDeRef(ref)).toBe(esperada);
  });
});
