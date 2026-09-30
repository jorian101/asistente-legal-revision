// Atajos globales de DocumentoPreview mientras se escribe en el editor de un bloque
// (un contenteditable de TipTap): no deben robarle Ctrl+Z, Ctrl+A ni Backspace.
// Antes solo excluían INPUT/TEXTAREA: Ctrl+Z borraba todas las ediciones pendientes y
// Backspace hacía preventDefault con el bloque seleccionado (no se podía borrar un carácter).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BloqueEsqueletoDTO } from "../api/formatos";
import DocumentoPreview from "../pages/admin/DocumentoPreview";

// jsdom no trae ResizeObserver y la barra flotante lo usa al seleccionar un bloque.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const BLOQUES: BloqueEsqueletoDTO[] = [
  {
    page: 0,
    index: 0,
    kind: "parrafo",
    align: "left",
    texto_plantilla: "Primer bloque",
    runs: [{ text: "Primer bloque" }],
  },
];

function renderConEditor() {
  const props = {
    onDeshacer: vi.fn(),
    onRehacer: vi.fn(),
    onEliminarSeleccion: vi.fn(),
  };
  const base = {
    bloques: BLOQUES,
    tamano: "carta" as const,
    puedeEditar: true,
    canDeshacer: true,
    ...props,
  };
  const { rerender } = render(<DocumentoPreview {...base} />);
  fireEvent.click(screen.getByText("Primer bloque")); // selecciona el bloque, como al editar
  rerender(
    <DocumentoPreview
      {...base}
      editandoKey="p0:i0"
      editorSlot={
        <div
          contentEditable
          suppressContentEditableWarning
          data-testid="editor"
        >
          texto
        </div>
      }
    />,
  );
  return { editor: screen.getByTestId("editor"), props };
}

describe("atajos dentro del editor de un bloque", () => {
  it("Ctrl+Z deshace en el editor, no descarta todas las ediciones", () => {
    const { editor, props } = renderConEditor();
    const ev = fireEvent.keyDown(editor, { key: "z", ctrlKey: true });
    expect(props.onDeshacer).not.toHaveBeenCalled();
    expect(ev).toBe(true); // no se hizo preventDefault: TipTap deshace lo tipeado
  });

  it("Backspace y Delete borran caracteres, no el bloque", () => {
    const { editor, props } = renderConEditor();
    expect(fireEvent.keyDown(editor, { key: "Backspace" })).toBe(true);
    expect(fireEvent.keyDown(editor, { key: "Delete" })).toBe(true);
    expect(props.onEliminarSeleccion).not.toHaveBeenCalled();
  });

  it("Ctrl+A selecciona el texto del editor, no todos los bloques", () => {
    const { editor } = renderConEditor();
    expect(fireEvent.keyDown(editor, { key: "a", ctrlKey: true })).toBe(true);
  });
});
