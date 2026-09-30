// Test ConfirmDialog: render condicional, botones y bloqueo en busy.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import ConfirmDialog from "../components/ConfirmDialog";

describe("ConfirmDialog", () => {
  it("no renderiza nada cuando open=false", () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="Borrar"
        message="¿Seguro?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("muestra título y mensaje, y dispara onConfirm", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Borrar"
        message="¿Eliminar el fragmento?"
        confirmLabel="Eliminar"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );

    expect(screen.getByRole("dialog", { name: "Borrar" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("cancela y desarma el lado del backdrop", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Borrar"
        message="x"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );

    await user.click(screen.getByRole("button", { name: /^cancelar$/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("deshabilita botones mientras busy=true", () => {
    render(
      <ConfirmDialog
        open
        title="Borrar"
        message="x"
        busy
        confirmLabel="Eliminar"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /procesando/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancelar/i })).toBeDisabled();
  });
});