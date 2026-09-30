// SelectorFuentes: modal común del chat para fijar normas, jurisprudencia o doctrina.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SelectorFuentes } from "../components/chat/SelectorFuentes";

vi.mock("../api/fuentes", async (orig) => ({
  ...(await orig<typeof import("../api/fuentes")>()),
  listarFuentes: vi.fn(),
  seleccionarFuente: vi.fn(),
}));
vi.mock("../api/doctrina", () => ({
  listarRecomendadasExpediente: vi.fn().mockResolvedValue([]),
}));
vi.mock("../lib/toasts", () => ({ toast: vi.fn() }));

import { listarRecomendadasExpediente } from "../api/doctrina";
import { listarFuentes, seleccionarFuente } from "../api/fuentes";

const f = (extra: Record<string, unknown> = {}) => ({
  id: 1,
  abreviatura: "LIB-A",
  nombre: "Libro A",
  categoria: "doctrina",
  subgrupo: null,
  estado_visibilidad: "global",
  propietario_id: null,
  es_propia: false,
  motivo_rechazo: null,
  ...extra,
});

beforeEach(() => {
  vi.clearAllMocks();
  (listarRecomendadasExpediente as ReturnType<typeof vi.fn>).mockResolvedValue(
    [],
  );
});

describe("SelectorFuentes", () => {
  it("fija una fuente y devuelve su abreviatura", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([f()]);
    (seleccionarFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    const onSeleccionada = vi.fn();
    render(
      <SelectorFuentes
        abierto
        categoria="doctrina"
        expedienteId={8}
        onCerrar={() => {}}
        onSeleccionada={onSeleccionada}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "Fijar" }));

    await waitFor(() => expect(seleccionarFuente).toHaveBeenCalledWith(1, 8));
    expect(onSeleccionada).toHaveBeenCalledWith("LIB-A");
  });

  it("sin expediente fija a la consulta (expediente null)", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([f()]);
    (seleccionarFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render(
      <SelectorFuentes
        abierto
        categoria="doctrina"
        expedienteId={null}
        onCerrar={() => {}}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "Fijar" }));

    await waitFor(() =>
      expect(seleccionarFuente).toHaveBeenCalledWith(1, null),
    );
  });

  it("agrupa la jurisprudencia en TCP y CIDH", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      f({
        id: 1,
        nombre: "SCP 0623",
        categoria: "jurisprudencia",
        subgrupo: "tcp",
      }),
      f({
        id: 2,
        nombre: "Caso TC vs Perú",
        categoria: "jurisprudencia",
        subgrupo: "cidh",
      }),
    ]);
    render(
      <SelectorFuentes
        abierto
        categoria="jurisprudencia"
        expedienteId={null}
        onCerrar={() => {}}
      />,
    );

    expect(await screen.findByText("Sentencias del TCP")).toBeInTheDocument();
    expect(screen.getByText("Sentencias de la Corte IDH")).toBeInTheDocument();
    expect(screen.getByText("SCP 0623")).toBeInTheDocument();
  });

  it("muestra solo las recomendadas de su categoría", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([f()]);
    (
      listarRecomendadasExpediente as ReturnType<typeof vi.fn>
    ).mockResolvedValue([
      {
        id: 1,
        nombre_archivo: "Libro A",
        corpus: "doctrina",
        corpus_ref: "LIB-A",
      },
      {
        id: 2,
        nombre_archivo: "SCP X",
        corpus: "jurisprudencia",
        corpus_ref: "SCP-X",
      },
    ]);
    render(
      <SelectorFuentes
        abierto
        categoria="doctrina"
        expedienteId={8}
        onCerrar={() => {}}
      />,
    );

    expect(
      await screen.findByText("Recomendadas para este expediente"),
    ).toBeInTheDocument();
    expect(screen.queryByText("SCP X")).toBeNull();
  });

  it("se cierra con Escape y no renderiza cerrado", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const onCerrar = vi.fn();
    const { rerender } = render(
      <SelectorFuentes
        abierto
        categoria="norma"
        expedienteId={null}
        onCerrar={onCerrar}
      />,
    );

    await userEvent.keyboard("{Escape}");
    expect(onCerrar).toHaveBeenCalled();

    rerender(
      <SelectorFuentes
        abierto={false}
        categoria="norma"
        expedienteId={null}
        onCerrar={onCerrar}
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("filtra por nombre o abreviatura con el buscador", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      f({ id: 1, nombre: "Código Penal Militar", abreviatura: "CPM" }),
      f({ id: 2, nombre: "Ley Orgánica", abreviatura: "LOFA" }),
    ]);
    render(
      <SelectorFuentes
        abierto
        categoria="norma"
        expedienteId={null}
        onCerrar={() => {}}
      />,
    );

    await userEvent.type(
      await screen.findByRole("searchbox", { name: "Buscar normas" }),
      "codigo",
    );

    expect(screen.getByText("Código Penal Militar")).toBeInTheDocument();
    expect(screen.queryByText("Ley Orgánica")).toBeNull();
  });

  it("una fuente ya fijada se muestra como Fijada y un click la quita", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([f()]);
    const onDesfijar = vi.fn();
    render(
      <SelectorFuentes
        abierto
        categoria="doctrina"
        expedienteId={null}
        onCerrar={() => {}}
        fijadas={["LIB-A"]}
        onDesfijar={onDesfijar}
      />,
    );

    await userEvent.click(
      await screen.findByRole("button", { name: /Quitar/ }),
    );

    expect(onDesfijar).toHaveBeenCalledWith("LIB-A");
    expect(seleccionarFuente).not.toHaveBeenCalled();
    expect(screen.getByText(/1 fijada/)).toBeInTheDocument();
  });
});
