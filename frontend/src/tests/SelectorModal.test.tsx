// SelectorModal: buscador (sin tildes ni mayúsculas), filtro segmentado,
// aviso de truncado y elección por id.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SelectorModal } from "../components/ui";

const OPCIONES = [
  {
    id: "1",
    titulo: "Nº 101/2026",
    detalle: "Pérez · Deserción",
    segmento: "activo",
  },
  {
    id: "2",
    titulo: "Nº 102/2026",
    detalle: "Gómez · Abandono",
    segmento: "archivado",
  },
  {
    id: "3",
    titulo: "Nº 103/2026",
    detalle: "Rojas · Insubordinación",
    segmento: "activo",
  },
];

function renderSelector(onSeleccionar = vi.fn()) {
  render(
    <SelectorModal
      open
      title="Elegir expediente"
      opciones={OPCIONES}
      segmentos={[
        ["activo", "Activos"],
        ["archivado", "Archivados"],
      ]}
      placeholder="Buscar expediente"
      aviso="Se muestran los 3 más recientes de 250."
      onSeleccionar={onSeleccionar}
      onClose={vi.fn()}
    />,
  );
  return within(screen.getByRole("list", { name: "Elegir expediente" }));
}

describe("SelectorModal", () => {
  it("filtra por texto ignorando tildes y mayúsculas", async () => {
    const lista = renderSelector();
    await userEvent.type(screen.getByLabelText("Buscar expediente"), "perez");
    expect(lista.getAllByRole("button")).toHaveLength(1);
    expect(lista.getByText("Nº 101/2026")).toBeInTheDocument();
  });

  it("filtra por segmento y muestra vacío si no hay coincidencias", async () => {
    const lista = renderSelector();
    await userEvent.click(screen.getByRole("radio", { name: "Archivados" }));
    expect(lista.getAllByRole("button")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("Buscar expediente"), "rojas");
    expect(screen.getByText("Sin resultados.")).toBeInTheDocument();
  });

  it("muestra el aviso de truncado y devuelve el id elegido", async () => {
    const onSeleccionar = vi.fn();
    const lista = renderSelector(onSeleccionar);
    expect(screen.getByText(/de 250/)).toBeInTheDocument();
    await userEvent.click(lista.getByRole("button", { name: /Nº 103/ }));
    expect(onSeleccionar).toHaveBeenCalledWith("3");
  });
});
