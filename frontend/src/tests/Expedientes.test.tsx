// Test Expedientes: checklist de requisitos por tipo de caso en el modal de
// apertura (vault taxonomia A). Cubre:
// - Alert con nombres legibles al elegir tipo_proceso
// - Boton Aperturar disabled mientras falten tipos por cubrir
// - Enabled cuando los archivos cubren los requeridos
// - Alert rojo + disabled si GET /requisitos falla (nunca degrada a abierto)
// - Cada archivo lleva su select de tipo_documento real

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, describe, it, expect } from "vitest";

import Expedientes from "../pages/consultas/Expedientes";
import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { asignarArchivos, permisosDeTest } from "./helpers";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";

vi.mock("../api/expedientes", () => ({
  abrirExpediente: vi.fn(),
  cambiarEstadoExpediente: vi.fn(),
  cargarObra: vi.fn(),
  editarExpediente: vi.fn(),
  eliminarObra: vi.fn(),
  getRequisitos: vi.fn(),
  listarExpedientes: vi.fn(),
  listarHistorialExpediente: vi.fn(),
  publicarObra: vi.fn(),
}));

vi.mock("../lib/toasts", () => ({
  toast: vi.fn(),
}));

vi.mock("../api/borradores", () => ({
  listarBorradores: vi.fn().mockResolvedValue([]),
  TIPO_BORRADOR_LABEL: {},
}));

vi.mock("../api/doctrina", () => ({
  listarDoctrinaPrivadaExpediente: vi.fn().mockResolvedValue([]),
  descargarObra: vi.fn(),
}));

import {
  abrirExpediente,
  cargarObra,
  getRequisitos,
  listarExpedientes,
} from "../api/expedientes";
import { toast as mockedToast } from "../lib/toasts";

// Permisos del render; un test puede denegar operaciones antes de renderizar.
let permisos = permisosDeTest();

const mockedToastFn = mockedToast as ReturnType<typeof vi.fn>;

const mockedGetRequisitos = getRequisitos as ReturnType<typeof vi.fn>;
const mockedListar = listarExpedientes as ReturnType<typeof vi.fn>;
const mockedAbrir = abrirExpediente as ReturnType<typeof vi.fn>;
const mockedCargar = cargarObra as ReturnType<typeof vi.fn>;

const REQUISITOS_CONSULTA = {
  tipo_proceso: "consulta",
  requeridos: ["sentencia", "acta_audiencia", "oficio_elevacion"],
  nombres: [
    "Sentencia (N° y fecha)",
    "Acta de Audiencia Pública de Lectura",
    "Oficio de Elevación del TPJM",
  ],
};

const PAGINA_VACIA = {
  items: [],
  total: 0,
  pagina: 1,
  por_pagina: 10,
};

function renderExpedientes() {
  const value: AuthState = {
    access_token: "test-token",
    rol: "supervisor",
    carnet: "9000001",
    nombre: "Supervisor Prueba",
    id: 1,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <PermisosContext.Provider value={permisos}>
        <MemoryRouter>
          <Expedientes />
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
}

async function abrirForm() {
  await userEvent.click(
    screen.getByRole("button", { name: /abrir expediente/i }),
  );
}

beforeEach(() => {
  permisos = permisosDeTest();
  vi.clearAllMocks();
  mockedListar.mockResolvedValue(PAGINA_VACIA);
  mockedToastFn.mockClear();
});

describe("Apertura de expedientes — checklist de requisitos", () => {
  it("muestra el alert con nombres legibles al elegir tipo consulta", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    renderExpedientes();
    await abrirForm();

    await screen.findByText(/requisitos para consulta/i);
    // Los nombres aparecen en la lista (el mensaje de faltantes también los
    // cita, por eso se usa getAllByText).
    for (const nombre of REQUISITOS_CONSULTA.nombres) {
      expect(screen.getAllByText(nombre).length).toBeGreaterThanOrEqual(1);
    }
    // Sin archivos aún: botón bloqueado y aviso visible.
    const abrirBtn = screen.getByRole("button", { name: /^Abrir$/ });
    expect(abrirBtn).toBeDisabled();
  });

  it("habilita Aperturar cuando los archivos cubren los tipos requeridos", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    renderExpedientes();
    await abrirForm();

    await screen.findByText(/requisitos para consulta/i);

    const input = document.getElementById("abrir-archivos") as HTMLInputElement;
    const mkFile = (name: string) =>
      new File(["contenido"], name, { type: "application/pdf" });

    // 3 archivos; los tipos default se preseleccionan en orden de requisitos.
    asignarArchivos(input, [mkFile("a.pdf"), mkFile("b.pdf"), mkFile("c.pdf")]);

    // Los selects por archivo quedaron renderizados.
    expect(screen.getByText("Tipo por archivo")).toBeInTheDocument();

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /^Abrir$/ });
      expect(btn).not.toBeDisabled();
    });
  });

  it("bloquea si un tipo requerido no fue cubierto (validacion por tipo real)", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    renderExpedientes();
    await abrirForm();

    await screen.findByText(/requisitos para consulta/i);

    const input = document.getElementById("abrir-archivos") as HTMLInputElement;
    asignarArchivos(input, [
      new File(["s"], "s.pdf", { type: "application/pdf" }),
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["o"], "o.pdf", { type: "application/pdf" }),
    ]);

    // Con los 3 tipos default cubiertos -> habilitado.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Abrir$/ }),
      ).not.toBeDisabled();
    });

    // Validacion por TIPO REAL: cambiar un archivo a 'otro' deja de cubrir
    // su requisito -> vuelve a bloquearse aunque haya 3 archivos.
    // displayValue de un <select> es el TEXTO del option elegido.
    const selectSentencia = screen.getAllByDisplayValue("Sentencia")[0];
    await userEvent.selectOptions(selectSentencia, "otro");

    expect(screen.getByRole("button", { name: /^Abrir$/ })).toBeDisabled();
    expect(screen.getByText(/te faltan: sentencia/i)).toBeInTheDocument();
  });

  it("alert rojo y disabled si GET /requisitos falla (no degrada a abierto)", async () => {
    mockedGetRequisitos.mockRejectedValue(new Error("network down"));
    renderExpedientes();
    await abrirForm();

    expect(
      await screen.findByText(
        /no se pudieron cargar los requisitos\. no se puede aperturar hasta reintentar\./i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Abrir$/ })).toBeDisabled();
  });

  it("envia abrirExpediente y carga obras con su tipo real al aperturar", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    mockedAbrir.mockResolvedValue({
      expediente_id: 99,
      numero_caso: "T-001",
      estado: "activo",
      creado_at_iso: "2026-08-24T00:00:00Z",
    });
    mockedCargar.mockResolvedValue({
      obra_id: 1,
      estado_visibilidad: "publicado",
      estado_procesamiento: "completado",
      created_at_iso: "2026-08-24T00:00:00Z",
    });
    renderExpedientes();
    await abrirForm();
    await screen.findByText(/requisitos para consulta/i);

    // Llenar campos obligatorios minimos.
    await userEvent.type(
      document.getElementById("abrir-numero") as HTMLInputElement,
      "T-001",
    );
    await userEvent.type(
      document.getElementById("abrir-procesado") as HTMLInputElement,
      "Procesado Test",
    );
    const delitoSelect = document.getElementById(
      "abrir-delito",
    ) as HTMLSelectElement;
    await userEvent.selectOptions(delitoSelect, delitoSelect.options[1].value);

    const input = document.getElementById("abrir-archivos") as HTMLInputElement;
    asignarArchivos(input, [
      new File(["s"], "s.pdf", { type: "application/pdf" }),
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["o"], "o.pdf", { type: "application/pdf" }),
    ]);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Abrir$/ }),
      ).not.toBeDisabled();
    });
    await userEvent.click(screen.getByRole("button", { name: /^Abrir$/ }));

    await waitFor(() => {
      expect(mockedAbrir).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      // Los 3 archivos viajan con su tipo real (por orden de requisitos).
      expect(mockedCargar).toHaveBeenCalledTimes(3);
    });
    const tipos = mockedCargar.mock.calls.map((c) => c[0].tipo_documento);
    expect(tipos.sort()).toEqual([
      "acta_audiencia",
      "oficio_elevacion",
      "sentencia",
    ]);
  });
});

describe("Apertura tolerante a fallo por obra (bug 409/stale)", () => {
  async function llenarMinimos() {
    await userEvent.type(
      document.getElementById("abrir-numero") as HTMLInputElement,
      "T-100",
    );
    await userEvent.type(
      document.getElementById("abrir-procesado") as HTMLInputElement,
      "Procesado T",
    );
    const delitoSelect = document.getElementById(
      "abrir-delito",
    ) as HTMLSelectElement;
    await userEvent.selectOptions(delitoSelect, delitoSelect.options[1].value);
  }

  it("expediente creado aunque fallen obras: warning con detalle y refetch de lista", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    mockedAbrir.mockResolvedValue({
      expediente_id: 99,
      numero_caso: "T-100",
      estado: "activo",
      created_at_iso: "2026-08-24T00:00:00Z",
    });
    // Segunda carga falla; primera y tercera OK.
    mockedCargar
      .mockResolvedValueOnce({
        obra_id: 1,
        estado_visibilidad: "publicado",
        estado_procesamiento: "completado",
        created_at_iso: "",
      })
      .mockRejectedValueOnce(new Error("PDF corrupto"))
      .mockResolvedValueOnce({
        obra_id: 3,
        estado_visibilidad: "publicado",
        estado_procesamiento: "completado",
        created_at_iso: "",
      });

    renderExpedientes();
    await abrirForm();
    await screen.findByText(/requisitos para consulta/i);
    await llenarMinimos();

    const input = document.getElementById("abrir-archivos") as HTMLInputElement;
    asignarArchivos(input, [
      new File(["s"], "s.pdf", { type: "application/pdf" }),
      new File(["r"], "roto.pdf", { type: "application/pdf" }),
      new File(["o"], "o.pdf", { type: "application/pdf" }),
    ]);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Abrir$/ }),
      ).not.toBeDisabled();
    });
    await userEvent.click(screen.getByRole("button", { name: /^Abrir$/ }));

    await waitFor(() => {
      expect(mockedToastFn).toHaveBeenCalledWith(
        expect.stringContaining("Expediente T-100 creado con 2/3 obrados"),
        "warning",
      );
    });
    expect(mockedToastFn).toHaveBeenCalledWith(
      expect.stringContaining("roto.pdf"),
      "warning",
    );
    // El expediente NO se vuelve a crear: abrirExpediente una sola vez.
    expect(mockedAbrir).toHaveBeenCalledTimes(1);
    // Refetch explícito de lista tras el alta (initial + post-submit).
    await waitFor(() => {
      expect(mockedListar.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("409 en apertura mantiene el modal abierto y no carga obras", async () => {
    mockedGetRequisitos.mockResolvedValue(REQUISITOS_CONSULTA);
    const err = Object.assign(new Error("dup"), {
      response: { status: 409 },
    });
    mockedAbrir.mockRejectedValue(err);

    renderExpedientes();
    await abrirForm();
    await screen.findByText(/requisitos para consulta/i);
    await llenarMinimos();

    const input = document.getElementById("abrir-archivos") as HTMLInputElement;
    asignarArchivos(input, [
      new File(["s"], "s.pdf", { type: "application/pdf" }),
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["o"], "o.pdf", { type: "application/pdf" }),
    ]);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Abrir$/ }),
      ).not.toBeDisabled();
    });
    await userEvent.click(screen.getByRole("button", { name: /^Abrir$/ }));

    await waitFor(() => {
      expect(mockedToastFn).toHaveBeenCalledWith(
        expect.stringContaining("Ya existe un expediente"),
        "error",
      );
    });
    expect(mockedCargar).not.toHaveBeenCalled();
    // Modal sigue abierto (form visible).
    expect(screen.getByText(/requisitos para consulta/i)).toBeInTheDocument();
  });
});
