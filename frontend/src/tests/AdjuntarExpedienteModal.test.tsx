// AdjuntarExpedienteModal (chat): aviso de truncado, vacío y elección.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { listarExpedientes } from "../api/expedientes";
import { AdjuntarExpedienteModal } from "../components/chat/AdjuntarExpedienteModal";

vi.mock("../api/expedientes", () => ({ listarExpedientes: vi.fn() }));
const mocked = listarExpedientes as ReturnType<typeof vi.fn>;

const EXP = {
  id: 8,
  numero_caso: "9999",
  procesado_nombre: "Pérez",
  delito: "Deserción",
  estado: "activo",
};

describe("AdjuntarExpedienteModal", () => {
  it("avisa si la lista vino truncada y devuelve el expediente elegido", async () => {
    mocked.mockResolvedValue({
      items: [EXP],
      total: 250,
      pagina: 1,
      por_pagina: 100,
    });
    const onSeleccionar = vi.fn();
    render(
      <AdjuntarExpedienteModal
        abierto
        onCerrar={vi.fn()}
        onSeleccionar={onSeleccionar}
      />,
    );

    expect(
      await screen.findByText(/1 más recientes de 250/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /3145/ }));
    expect(onSeleccionar).toHaveBeenCalledWith(EXP);
  });

  it("invita a abrir un expediente si no hay ninguno", async () => {
    mocked.mockResolvedValue({
      items: [],
      total: 0,
      pagina: 1,
      por_pagina: 100,
    });
    render(
      <AdjuntarExpedienteModal
        abierto
        onCerrar={vi.fn()}
        onSeleccionar={vi.fn()}
      />,
    );
    expect(await screen.findByText(/No tenés expedientes/)).toBeInTheDocument();
    expect(screen.queryByText(/más recientes/)).toBeNull();
  });
});
