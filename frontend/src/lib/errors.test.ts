// Test del util mensajeError — extracción de errores de validación pydantic/FastAPI.

import { describe, expect, it } from "vitest";

import { mensajeError } from "./errors";

describe("mensajeError", () => {
  it("devuelve el detail string cuando es string", () => {
    const err = { response: { data: { detail: "Carnet invalido" } } };
    expect(mensajeError(err, "fallback")).toBe("Carnet invalido");
  });

  it("extrae el primer msg de un detail array (422 pydantic)", () => {
    const err = {
      response: {
        data: {
          detail: [
            {
              type: "string_too_short",
              loc: ["body", "carnet"],
              msg: "String should have at least 4 characters",
              input: "",
            },
          ],
        },
      },
    };
    expect(mensajeError(err, "fallback")).toBe(
      "String should have at least 4 characters",
    );
  });

  it("usa el fallback cuando no hay detalle reconocible", () => {
    expect(mensajeError(new Error("network"), "fallback")).toBe("fallback");
    expect(
      mensajeError({ response: { data: { detail: [] } } }, "fallback"),
    ).toBe("fallback");
  });
});
