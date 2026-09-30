// Página de Fuentes: flujo común privada -> pendiente -> global para normas,
// jurisprudencia y doctrina. El operador propone; el supervisor aprueba o rechaza.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { permisosDeTest } from "./helpers";
import { setAuthState } from "../api/auth";
import Fuentes from "../pages/consultas/Fuentes";
import type { AuthState } from "../api/auth";

vi.mock("../api/fuentes", async (orig) => ({
  ...(await orig<typeof import("../api/fuentes")>()),
  listarFuentes: vi.fn(),
  listarResolucionesTribunal: vi.fn().mockResolvedValue([]),
  proponerFuente: vi.fn(),
  resolverFuente: vi.fn(),
  seleccionarFuente: vi.fn(),
  recomendarFuente: vi.fn(),
  subirFuente: vi.fn(),
}));
vi.mock("../api/jobs", () => ({
  obtenerTrabajo: vi.fn(),
  cancelarTrabajo: vi.fn(),
}));
vi.mock("../api/expedientes", async (orig) => ({
  ...(await orig<typeof import("../api/expedientes")>()),
  listarExpedientes: vi.fn().mockResolvedValue({
    items: [{ id: 8, numero_caso: "9999" }],
    total: 1,
    pagina: 1,
    por_pagina: 100,
  }),
  listarPromocionesPendientes: vi.fn().mockResolvedValue([]),
  resolverPromocion: vi.fn(),
}));
vi.mock("../api/doctrina", () => ({
  listarRecomendacionesPendientes: vi.fn().mockResolvedValue([]),
  aprobarRecomendacion: vi.fn(),
  rechazarRecomendacion: vi.fn(),
  aprobarTodasRecomendaciones: vi.fn(),
}));
vi.mock("../lib/toasts", () => ({ toast: vi.fn() }));

import {
  listarFuentes,
  proponerFuente,
  recomendarFuente,
  resolverFuente,
  seleccionarFuente,
  subirFuente,
} from "../api/fuentes";
import { cancelarTrabajo, obtenerTrabajo } from "../api/jobs";

// Permisos del render; un test puede denegar operaciones antes de renderizar.
let permisos = permisosDeTest();

const fuente = (extra: Record<string, unknown> = {}) => ({
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

function render_(rol: "supervisor" | "operador_juridico") {
  const value: AuthState = {
    access_token: "t",
    rol,
    carnet: "1",
    nombre: "Prueba",
    id: 3,
  };
  setAuthState(value);
  render(
    <AuthProvider>
      <PermisosContext.Provider value={permisos}>
        <MemoryRouter>
          <Fuentes />
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
}

async function irADoctrina() {
  await userEvent.click(await screen.findByRole("tab", { name: "Doctrina" }));
}

beforeEach(() => {
  permisos = permisosDeTest();
  vi.clearAllMocks();
  (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([]);
});

// Abre el picker de expediente del panel y elige por número de caso.
async function elegirExpediente(numero: string) {
  await userEvent.click(
    screen.getByRole("button", { name: "Sin expediente (consulta)" }),
  );
  const dialogo = await screen.findByRole("dialog", {
    name: "Elegir expediente",
  });
  await userEvent.click(
    within(dialogo).getByRole("button", { name: new RegExp(numero) }),
  );
}

function jobCompletado(extra: Record<string, unknown> = {}) {
  return {
    id: "j1",
    tipo: "fuente",
    estado: "completado",
    cancelacion_solicitada: false,
    iniciado_en: "2026-09-22T00:00:00Z",
    terminado_en: "2026-09-22T00:00:05Z",
    error: null,
    resultado: null,
    ...extra,
  };
}

describe("Fuentes — pestañas por rol", () => {
  it("el operador ve normas, jurisprudencia y doctrina", async () => {
    render_("operador_juridico");

    for (const nombre of ["Normas", "Jurisprudencia", "Doctrina"]) {
      expect(
        await screen.findByRole("tab", { name: nombre }),
      ).toBeInTheDocument();
    }
    expect(
      screen.queryByRole("tab", { name: "Obrados propuestos" }),
    ).toBeNull();
    expect(screen.queryByRole("tab", { name: "Fuentes sugeridas" })).toBeNull();
  });

  it("el supervisor ve además las colas de recomendaciones y promociones", async () => {
    render_("supervisor");

    expect(
      await screen.findByRole("tab", { name: "Fuentes sugeridas" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Obrados propuestos" }),
    ).toBeInTheDocument();
  });
});

describe("Fuentes — flujo del operador", () => {
  it("propone su fuente privada y no puede aprobar", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      fuente({ estado_visibilidad: "privado", es_propia: true }),
    ]);
    (proponerFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render_("operador_juridico");
    await irADoctrina();

    await userEvent.click(
      await screen.findByRole("button", { name: "Proponer" }),
    );

    await waitFor(() => expect(proponerFuente).toHaveBeenCalledWith(1));
    expect(screen.queryByRole("button", { name: "Aprobar" })).toBeNull();
  });

  it("solo ofrece proponer lo propio y privado", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      fuente({ id: 1, estado_visibilidad: "global" }),
      fuente({ id: 2, estado_visibilidad: "privado", es_propia: false }),
    ]);
    render_("operador_juridico");
    await irADoctrina();

    await screen.findAllByText("Libro A");
    expect(screen.queryByRole("button", { name: "Proponer" })).toBeNull();
  });

  it("sin doctrina.crear no ofrece fijar ni subir", async () => {
    permisos = permisosDeTest(["doctrina.crear"]);
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([fuente()]);
    render_("operador_juridico");
    await irADoctrina();

    await screen.findAllByText("Libro A");
    expect(screen.queryByRole("button", { name: "Fijar" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Subir/ })).toBeNull();
  });

  it("fija una fuente a la consulta o al expediente elegido", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([fuente()]);
    (seleccionarFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render_("operador_juridico");
    await irADoctrina();

    await userEvent.click(await screen.findByRole("button", { name: "Fijar" }));
    await waitFor(() =>
      expect(seleccionarFuente).toHaveBeenCalledWith(1, null),
    );

    await elegirExpediente("9999");
    await userEvent.click(screen.getByRole("button", { name: "Fijar" }));
    await waitFor(() =>
      expect(seleccionarFuente).toHaveBeenLastCalledWith(1, 8),
    );
  });

  it("recomendar exige elegir un expediente", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([fuente()]);
    (recomendarFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render_("operador_juridico");
    await irADoctrina();

    const recomendar = await screen.findByRole("button", {
      name: "Recomendar",
    });
    expect(recomendar).toBeDisabled();

    await elegirExpediente("9999");
    await userEvent.click(screen.getByRole("button", { name: "Recomendar" }));
    await waitFor(() =>
      expect(recomendarFuente).toHaveBeenCalledWith("doctrina", "LIB-A", 8),
    );
  });
});

describe("Fuentes — flujo del supervisor", () => {
  it("aprueba una fuente pendiente", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      fuente({ estado_visibilidad: "pendiente" }),
    ]);
    (resolverFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render_("supervisor");
    await irADoctrina();

    await userEvent.click(
      await screen.findByRole("button", { name: "Aprobar" }),
    );

    await waitFor(() => expect(resolverFuente).toHaveBeenCalledWith(1, true));
  });

  it("rechazar exige un motivo", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      fuente({ estado_visibilidad: "pendiente" }),
    ]);
    (resolverFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render_("supervisor");
    await irADoctrina();

    await userEvent.click(
      await screen.findByRole("button", { name: "Rechazar" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar rechazo" }),
    );
    expect(resolverFuente).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByLabelText("Motivo del rechazo"),
      "No es un libro",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar rechazo" }),
    );

    await waitFor(() =>
      expect(resolverFuente).toHaveBeenCalledWith(1, false, "No es un libro"),
    );
  });
});

describe("Fuentes — subida y jurisprudencia", () => {
  it("el operador sube como privada y la norma pide jerarquía", async () => {
    (subirFuente as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "j1",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue(
      jobCompletado(),
    );
    render_("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Subir norma" }),
    );
    const form = screen.getByRole("form", { name: /subir norma/i });
    expect(within(form).getByLabelText("Jerarquía")).toBeInTheDocument();
    expect(
      within(form).getByRole("button", { name: "Subir como privada" }),
    ).toBeDisabled();

    const archivo = new File(["x"], "ley.pdf", { type: "application/pdf" });
    await userEvent.upload(within(form).getByLabelText(/archivo/i), archivo);
    await userEvent.type(
      within(form).getByLabelText("Nombre"),
      "Ley de recursos",
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Subir como privada" }),
    );

    await waitFor(() =>
      expect(subirFuente).toHaveBeenCalledWith(
        expect.objectContaining({
          categoria: "norma",
          nombre: "Ley de recursos",
          jerarquia: "supletoria",
        }),
        expect.any(Function),
      ),
    );
  });

  it("el indexado en curso se puede cancelar", async () => {
    (subirFuente as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "j1",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jobCompletado({ estado: "en_curso" }))
      .mockResolvedValueOnce(jobCompletado({ estado: "cancelado" }));
    (cancelarTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue(
      jobCompletado({ estado: "cancelado" }),
    );
    render_("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Subir norma" }),
    );
    const form = screen.getByRole("form", { name: /subir norma/i });
    await userEvent.upload(
      within(form).getByLabelText(/archivo/i),
      new File(["x"], "ley.pdf", { type: "application/pdf" }),
    );
    await userEvent.type(
      within(form).getByLabelText("Nombre"),
      "Ley cancelable",
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Subir como privada" }),
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "Cancelar indexado" }),
    );
    await waitFor(() => expect(cancelarTrabajo).toHaveBeenCalledWith("j1"));
  });

  it("la jurisprudencia se divide en TCP, CIDH y resoluciones del tribunal", async () => {
    (listarFuentes as ReturnType<typeof vi.fn>).mockResolvedValue([
      fuente({
        id: 1,
        nombre: "SCP 0623",
        categoria: "jurisprudencia",
        subgrupo: "tcp",
      }),
      fuente({
        id: 2,
        nombre: "Caso TC vs Perú",
        categoria: "jurisprudencia",
        subgrupo: "cidh",
      }),
    ]);
    render_("operador_juridico");

    await userEvent.click(
      await screen.findByRole("tab", { name: "Jurisprudencia" }),
    );

    expect(await screen.findByText("Sentencias del TCP")).toBeInTheDocument();
    expect(screen.getByText("Sentencias de la Corte IDH")).toBeInTheDocument();
    expect(screen.getByText("Resoluciones del tribunal")).toBeInTheDocument();
    expect(screen.getByText("SCP 0623")).toBeInTheDocument();
  });
});
