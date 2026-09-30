// Test SeleccionarObrasModal: todas las obras marcadas por defecto, autor
// visible (instancia o usuario·cargo), y confirmación devuelve la selección.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, describe, it, expect } from "vitest";

import { SeleccionarObrasModal } from "../components/chat/SeleccionarObrasModal";
import { ToastContainer } from "../lib/toasts";

vi.mock("../api/expedientes", () => ({
  listarHistorialExpediente: vi.fn(),
}));

import { listarHistorialExpediente } from "../api/expedientes";

const mockedHistorial = listarHistorialExpediente as ReturnType<typeof vi.fn>;

const OBRAS = [
  {
    id: 1,
    expediente_id: 3,
    propietario_id: 7,
    tipo_documento: "sentencia",
    nombre_archivo: "sentencia.pdf",
    estado_visibilidad: "publicado",
    estado_procesamiento: "completado",
    es_propia: false,
    created_at_iso: "2026-08-15T10:00:00Z",
    autor_instancia: "Tribunal Permanente de Justicia Militar",
  },
  {
    id: 2,
    expediente_id: 3,
    propietario_id: 7,
    tipo_documento: "memorial_apelacion",
    nombre_archivo: "memorial.docx",
    estado_visibilidad: "privado",
    estado_procesamiento: "completado",
    es_propia: true,
    created_at_iso: "2026-08-15T11:00:00Z",
    autor_nombre: "Juan Pérez",
    autor_cargo: "Fiscal",
  },
];

function renderModal() {
  return render(
    <>
      <SeleccionarObrasModal
        expedienteId={3}
        inicial={null}
        onConfirmar={vi.fn()}
        onCerrar={vi.fn()}
      />
      <ToastContainer />
    </>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedHistorial.mockReset();
  mockedHistorial.mockResolvedValue({
    expediente_id: 3,
    obras: OBRAS,
    total: 2,
  });
});

// Checkboxes de obrados (sin el maestro "Seleccionar todas").
const obrados = () =>
  screen
    .getAllByRole("checkbox")
    .filter(
      (cb) => !cb.closest("label")?.textContent?.includes("Seleccionar todas"),
    );

describe("SeleccionarObrasModal", () => {
  it("al abrir, el foco entra al buscador del dialogo (teclado)", async () => {
    renderModal();
    await screen.findByText("sentencia.pdf");
    expect(
      screen.getByRole("searchbox", { name: "Buscar obrados" }),
    ).toHaveFocus();
  });

  it("Escape cierra el modal (teclado, WCAG 2.1.2)", async () => {
    const user = userEvent.setup();
    const onCerrar = vi.fn();
    render(
      <SeleccionarObrasModal
        expedienteId={3}
        inicial={null}
        onConfirmar={vi.fn()}
        onCerrar={onCerrar}
      />,
    );
    await screen.findByText("sentencia.pdf");
    await user.keyboard("{Escape}");
    expect(onCerrar).toHaveBeenCalledTimes(1);
  });

  it("muestra las obras con su autor (instancia o usuario·cargo)", async () => {
    renderModal();
    expect(await screen.findByText("sentencia.pdf")).toBeInTheDocument();
    expect(
      screen.getByText(/Tribunal Permanente de Justicia Militar/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Juan Pérez · Fiscal/)).toBeInTheDocument();
  });

  it("usa el término «obrados» en el título y el aria-label", async () => {
    renderModal();
    await screen.findByText("sentencia.pdf");
    expect(
      screen.getByRole("heading", { name: /Obrados del expediente/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("dialog", { name: "Obrados del expediente" }),
    ).toBeInTheDocument();
  });

  it("todas las obras vienen marcadas por defecto", async () => {
    renderModal();
    await screen.findByText("sentencia.pdf");
    const checkboxes = obrados();
    expect(checkboxes).toHaveLength(2);
    for (const cb of checkboxes) {
      expect(cb).toBeChecked();
    }
  });

  it("confirmar con todas marcadas devuelve null (todas)", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn();
    render(
      <SeleccionarObrasModal
        expedienteId={3}
        inicial={null}
        onConfirmar={onConfirmar}
        onCerrar={vi.fn()}
      />,
    );
    await screen.findByText("sentencia.pdf");
    await user.click(screen.getByRole("button", { name: "Aplicar selección" }));
    expect(onConfirmar).toHaveBeenCalledWith(null);
  });

  it("desmarcar una obra devuelve la lista sin esa obra", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn();
    render(
      <SeleccionarObrasModal
        expedienteId={3}
        inicial={null}
        onConfirmar={onConfirmar}
        onCerrar={vi.fn()}
      />,
    );
    await screen.findByText("sentencia.pdf");
    const checkboxes = obrados();
    await user.click(checkboxes[0]); // desmarcar sentencia
    await user.click(screen.getByRole("button", { name: "Aplicar selección" }));
    expect(onConfirmar).toHaveBeenCalledWith([2]);
  });

  it("respeta la selección previa de la conversación", async () => {
    render(
      <SeleccionarObrasModal
        expedienteId={3}
        inicial={[OBRAS[1].id]}
        onConfirmar={vi.fn()}
        onCerrar={vi.fn()}
      />,
    );
    await screen.findByText("sentencia.pdf");
    const [primera, segunda] = obrados();
    expect(primera).not.toBeChecked();
    expect(segunda).toBeChecked();
    expect(screen.getByText(/1 de 2 seleccionados/)).toBeInTheDocument();
  });
});

describe("Seleccionar todas", () => {
  it("queda indeterminado con selección parcial y vuelve a marcar todas", async () => {
    const user = userEvent.setup();
    renderModal();
    await screen.findByText("sentencia.pdf");
    const todas = screen.getByRole("checkbox", { name: "Seleccionar todas" });
    expect(todas).toBeChecked();

    await user.click(obrados()[0]);
    expect((todas as HTMLInputElement).indeterminate).toBe(true);

    await user.click(todas);
    expect(obrados().every((cb) => (cb as HTMLInputElement).checked)).toBe(
      true,
    );
    expect((todas as HTMLInputElement).indeterminate).toBe(false);
  });
});
