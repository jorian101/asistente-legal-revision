import { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import { EXTENSIONES_BLOQUE } from "./extensionesBloque";
import { textoDeDoc } from "./textoBloque";

let editores: Editor[] = [];
afterEach(() => {
  editores.forEach((e) => e.destroy());
  editores = [];
});

function texto(html: string, extensiones = EXTENSIONES_BLOQUE): string {
  const e = new Editor({ extensions: extensiones, content: html });
  editores.push(e);
  return textoDeDoc(e.state.doc, false);
}

describe("editor de bloque: nada que se acepte se pierde al guardar", () => {
  it("una lista (p. ej. pegada desde Word) conserva su texto", () => {
    const lista =
      "<ol><li><p>Antecedentes</p></li><li><p>Fundamentos</p></li></ol>";
    expect(texto(lista, [StarterKit])).toBe(""); // con el StarterKit completo se perdía
    expect(texto(lista)).toBe("Antecedentes\nFundamentos");
  });

  it("Shift+Enter (salto duro) se guarda como salto de línea", () => {
    expect(texto("<p>VISTOS:<br>El expediente</p>")).toBe(
      "VISTOS:\nEl expediente",
    );
  });

  it("cursiva y tachado no se pueden aplicar (el bloque no los guarda)", () => {
    const e = new Editor({
      extensions: EXTENSIONES_BLOQUE,
      content: "<p>texto</p>",
    });
    editores.push(e);
    expect(e.schema.marks.italic).toBeUndefined();
    expect(e.schema.marks.strike).toBeUndefined();
    expect(e.schema.marks.bold).toBeDefined();
    expect(e.schema.marks.underline).toBeDefined();
  });
});
