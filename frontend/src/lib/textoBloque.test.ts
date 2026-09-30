import { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import { segmentarNegrita, textoDeDoc } from "./textoBloque";

let editor: Editor | null = null;
afterEach(() => editor?.destroy());

function doc(html: string) {
  editor = new Editor({ extensions: [StarterKit], content: html });
  return editor.state.doc;
}

describe("textoDeDoc (lo que guarda el editor)", () => {
  it("conserva la negrita de una palabra como **…**", () => {
    expect(
      textoDeDoc(
        doc("<p>Se declara <strong>procedente</strong> la consulta</p>"),
        false,
      ),
    ).toBe("Se declara **procedente** la consulta");
  });

  it("un Enter separa líneas en vez de pegar las palabras", () => {
    expect(textoDeDoc(doc("<p>VISTOS:</p><p>El expediente</p>"), false)).toBe(
      "VISTOS:\nEl expediente",
    );
  });

  it("si todo el bloque es negrita no escribe asteriscos (va en el atributo bold)", () => {
    expect(textoDeDoc(doc("<p><strong>AUTO DE VISTA</strong></p>"), true)).toBe(
      "AUTO DE VISTA",
    );
  });
});

describe("segmentarNegrita (lo que pinta la vista previa)", () => {
  it("separa los tramos en negrita", () => {
    expect(segmentarNegrita("por el **Artículo 194** del CPPM")).toEqual([
      { texto: "por el ", negrita: false },
      { texto: "Artículo 194", negrita: true },
      { texto: " del CPPM", negrita: false },
    ]);
  });

  it("asteriscos sueltos quedan como texto", () => {
    expect(segmentarNegrita("Art. 5 * nota")).toEqual([
      { texto: "Art. 5 * nota", negrita: false },
    ]);
  });
});
