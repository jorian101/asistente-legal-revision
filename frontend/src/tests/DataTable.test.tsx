// Test DataTable: estados carga, vacío, buscador, filtros y paginación.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import DataTable, { type DataTableColumn } from "../components/DataTable";

interface Row {
  id: number;
  nombre: string;
  grupo: string;
}

const COLUMNS: DataTableColumn<Row>[] = [
  { key: "id", header: "#" },
  { key: "nombre", header: "Nombre" },
  {
    key: "grupo",
    header: "Grupo",
    render: (r) => <span>{r.grupo.toUpperCase()}</span>,
  },
];

const FILAS: Row[] = [
  { id: 1, nombre: "alpha", grupo: "a" },
  { id: 2, nombre: "beta", grupo: "b" },
];

function renderTable(overrides: Partial<React.ComponentProps<typeof DataTable<Row>>> = {}) {
  return render(
    <DataTable<Row>
      columns={COLUMNS}
      rowKey={(r) => r.id}
      rows={FILAS}
      emptyMessage="No hay filas"
      total={null}
      {...overrides}
    />
  );
}

describe("DataTable", () => {
  it("renderiza filas y columnas", () => {
    renderTable();

    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    // Columna render azul: grupo en mayúsculas.
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Nombre" })).toBeInTheDocument();
  });

  it("muestra esqueletos mientras rows=null", () => {
    renderTable({ rows: null });

    expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
    expect(document.querySelectorAll(".datatable__skeleton").length).toBeGreaterThan(0);
  });

  it("muestra mensaje de estado vacío cuando no hay filas", () => {
    renderTable({ rows: [] });
    expect(screen.getByText("No hay filas")).toBeInTheDocument();
  });

  it("dispara onSearchChange al escribir en el buscador", async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    renderTable({ onSearchChange });

    await user.type(screen.getByRole("searchbox"), "ab");
    expect(onSearchChange).toHaveBeenLastCalledWith("ab");
  });

  it("renderiza filtros del slot y muestra paginación cuando total > pageSize", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    renderTable({
      total: 25,
      page: 2,
      pageSize: 10,
      onPageChange,
      filtros: <button type="button">Filtro custom</button>,
    });

    expect(screen.getByRole("button", { name: "Filtro custom" })).toBeInTheDocument();
    expect(screen.getByText("Página 2 de 3")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "← Ant" })).not.toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Sig →" }));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("deshabilita paginación en la primera y última página", () => {
    renderTable({ total: 25, page: 3, pageSize: 10, onPageChange: vi.fn() });
    expect(screen.getByRole("button", { name: "← Ant" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Sig →" })).toBeDisabled();
  });
});