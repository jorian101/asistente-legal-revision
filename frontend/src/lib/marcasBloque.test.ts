import { Editor } from "@tiptap/react";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import { todoConMarca } from "./marcasBloque";

let editor: Editor | null = null;
afterEach(() => editor?.destroy());

function crear(html: string): Editor {
  editor = new Editor({ extensions: [StarterKit, Underline], content: html });
  return editor;
}

describe("todoConMarca (negrita/subrayado de todo el bloque)", () => {
  it("bloque entero en negrita: true aunque el cursor esté al inicio", () => {
    const e = crear("<p><strong>AUTO DE VISTA</strong></p>");
    e.commands.setTextSelection(1);
    expect(todoConMarca(e.state.doc, "bold")).toBe(true);
  });

  it("una sola palabra en negrita: el bloque NO es negrita, aunque el cursor esté en ella", () => {
    const e = crear(
      "<p>Se declara <strong>procedente</strong> la consulta</p>",
    );
    e.commands.setTextSelection(15); // dentro de "procedente": isActive('bold') daría true
    expect(e.isActive("bold")).toBe(true);
    expect(todoConMarca(e.state.doc, "bold")).toBe(false);
  });

  it("subrayado y bloque vacío", () => {
    expect(
      todoConMarca(crear("<p><u>Texto</u></p>").state.doc, "underline"),
    ).toBe(true);
    expect(todoConMarca(crear("<p></p>").state.doc, "bold")).toBe(false);
  });
});
