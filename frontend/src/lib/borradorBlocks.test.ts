import { describe, expect, it } from "vitest";

import { textoPlano } from "./borradorBlocks";

describe("textoPlano (resumen de la tarjeta de obrado)", () => {
  it("quita la negrita y el código en línea", () => {
    expect(
      textoPlano(
        "regulada por el **Artículo 194 del CPPM**, con `nota` y __otra__",
      ),
    ).toBe("regulada por el Artículo 194 del CPPM, con nota y otra");
  });

  it("quita los # de encabezado y los > de cita al inicio de línea", () => {
    expect(textoPlano("## VISTOS\n> cita\ntexto")).toBe("VISTOS\ncita\ntexto");
  });

  it("no toca asteriscos sueltos ni el texto normal", () => {
    expect(textoPlano("Art. 5 * nota al pie")).toBe("Art. 5 * nota al pie");
  });
});
