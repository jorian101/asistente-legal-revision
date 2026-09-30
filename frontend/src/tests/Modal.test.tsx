// Modal: anatomía (título, cerrar, pie) y teclado con diálogos apilados.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ConfirmDialog from "../components/ConfirmDialog";
import { Modal } from "../components/ui";

describe("Modal", () => {
  it("rotula el diálogo con su título y el botón × lo cierra", () => {
    const onClose = vi.fn();
    render(
      <Modal
        open
        title="Editar norma"
        onClose={onClose}
        footer={<button>Ok</button>}
      >
        <input aria-label="Nombre" />
      </Modal>,
    );
    expect(
      screen.getByRole("dialog", { name: "Editar norma" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre")).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("con un ConfirmDialog encima, Escape solo cierra el de arriba", () => {
    const onClose = vi.fn();
    const onCancel = vi.fn();
    render(
      <Modal open title="Chats archivados" onClose={onClose}>
        <ConfirmDialog
          open
          title="Eliminar"
          message="¿Seguro?"
          onConfirm={vi.fn()}
          onCancel={onCancel}
        />
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });
});
