// Criterios (admin): ver y editar los criterios del asistente.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CriteriosAdmin from "../pages/admin/Criterios";

vi.mock("../api/doctrina", () => ({
  listarCriterios: vi.fn(),
  actualizarCriterio: vi.fn(),
  descargarObra: vi.fn(),
}));
vi.mock("../lib/toasts", () => ({ toast: vi.fn() }));

import {
  actualizarCriterio,
  descargarObra,
  listarCriterios,
} from "../api/doctrina";

const criterio = {
  id: 22,
  nombre_archivo: "criterio-argumentacion.md",
  contenido_texto:
    "---\ntitulo: x\n---\n# Criterio\nResponder todos los agravios.",
  procedencia: "criterio-vocal",
  recomendada: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (listarCriterios as ReturnType<typeof vi.fn>).mockResolvedValue([criterio]);
});

describe("Criterios (admin)", () => {
  it("lista los criterios y oculta el frontmatter", async () => {
    render(<CriteriosAdmin />);

    expect(
      await screen.findByText(/criterio-argumentacion\.md/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/titulo: x/)).toBeNull();
  });

  it("edita el texto y lo guarda", async () => {
    (actualizarCriterio as ReturnType<typeof vi.fn>).mockResolvedValue(
      criterio,
    );
    render(<CriteriosAdmin />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Editar" }),
    );
    const area = document.querySelector("textarea") as HTMLTextAreaElement;
    await userEvent.clear(area);
    await userEvent.type(area, "Texto nuevo");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() =>
      expect(actualizarCriterio).toHaveBeenCalledWith(
        22,
        expect.objectContaining({ contenido_texto: "Texto nuevo" }),
      ),
    );
  });

  it("cancelar la edición no guarda", async () => {
    render(<CriteriosAdmin />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Editar" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(actualizarCriterio).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
  });

  it("descarga el criterio", async () => {
    render(<CriteriosAdmin />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Descargar" }),
    );

    expect(descargarObra).toHaveBeenCalledWith(22);
  });
});
