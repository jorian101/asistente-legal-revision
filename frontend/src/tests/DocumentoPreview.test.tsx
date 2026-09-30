// DocumentoPreview: sin formatos.actualizar queda en solo lectura — sin
// "Guardar todo", sin drag-handle para reordenar y sin editar márgenes.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DocumentoPreview from "../pages/admin/DocumentoPreview";
import type { BloqueEsqueletoDTO } from "../api/formatos";

const BLOQUES: BloqueEsqueletoDTO[] = [
  {
    page: 0,
    index: 0,
    kind: "parrafo",
    align: "left",
    texto_plantilla: "Primer bloque {{NUMERO}}",
    runs: [{ text: "Primer bloque {{NUMERO}}" }],
  },
  {
    page: 0,
    index: 1,
    kind: "parrafo",
    align: "left",
    texto_plantilla: "Segundo bloque",
    runs: [{ text: "Segundo bloque" }],
  },
];

function renderPreview(puedeEditar: boolean, hayCambios = false) {
  return render(
    <DocumentoPreview
      bloques={BLOQUES}
      tamano="carta"
      onGuardarTodo={vi.fn()}
      onCancelarLocal={vi.fn()}
      onReordenar={vi.fn()}
      onAplicarSeleccion={vi.fn()}
      onMargenesChange={vi.fn()}
      onAbrirMargenesManual={vi.fn()}
      hayCambios={hayCambios}
      puedeEditar={puedeEditar}
    />,
  );
}

describe("DocumentoPreview según permiso", () => {
  it("sin permiso: sin Guardar todo, sin drag-handle y márgenes deshabilitados", () => {
    const { container } = renderPreview(false);

    expect(screen.getByText("Segundo bloque")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar todo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull();
    expect(container.querySelectorAll(".doc-preview__handle")).toHaveLength(0);
    expect(screen.getByLabelText("Preset de márgenes")).toBeDisabled();
    expect(
      container.querySelector('[title="Ajustar márgenes manualmente"]'),
    ).toBeNull();
  });

  it("con permiso: Guardar todo, drag-handle y márgenes habilitados", () => {
    const { container } = renderPreview(true, true);

    expect(screen.getByRole("button", { name: "Guardar todo" })).toBeEnabled();
    expect(container.querySelectorAll(".doc-preview__handle")).toHaveLength(
      BLOQUES.length,
    );
    expect(screen.getByLabelText("Preset de márgenes")).toBeEnabled();
  });
});
