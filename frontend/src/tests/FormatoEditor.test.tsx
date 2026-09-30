// FormatoEditor: sin formatos.actualizar queda en solo lectura (sin barra de
// formato ni Guardar, no editable y sin emitir cambios); con permiso, edita.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import FormatoEditor from "../pages/admin/FormatoEditor";

function renderEditor(puedeEditar: boolean, modo: "panel" | "inline") {
  const props = {
    inicial: "Texto del bloque {{NUMERO}}",
    onGuardar: vi.fn(),
    onCancelar: vi.fn(),
    onCambio: vi.fn(),
    modo,
    puedeEditar,
  };
  const utils = render(<FormatoEditor {...props} />);
  return { ...utils, props };
}

describe("FormatoEditor según permiso", () => {
  it.each(["panel", "inline"] as const)(
    "sin permiso (%s): solo lectura, sin Guardar y sin emitir cambios",
    async (modo) => {
      const { container, props } = renderEditor(false, modo);

      expect(await screen.findByText(/Texto del bloque/)).toBeInTheDocument();
      expect(container.querySelector("[contenteditable='true']")).toBeNull();
      expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Centro" })).toBeNull();
      expect(props.onCambio).not.toHaveBeenCalled();

      await userEvent.click(screen.getByRole("button", { name: "Cerrar" }));
      expect(props.onCancelar).toHaveBeenCalled();
    },
  );

  it("con permiso: editable, con barra de formato y Guardar", async () => {
    const { container } = renderEditor(true, "panel");

    expect(await screen.findByText(/Texto del bloque/)).toBeInTheDocument();
    expect(container.querySelector("[contenteditable='true']")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Centro" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
  });
});
