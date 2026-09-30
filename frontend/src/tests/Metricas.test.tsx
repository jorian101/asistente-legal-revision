// Test Dashboard (admin): resumen general del asistente.
// Cubre: KPI cards, barra de salud, chart por día, modelos activos,
// distribución de uso, adopción por usuario, sección Infraestructura
// (HU-22 salud PG/Qdrant/SSE), estado vacío y error.

import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import Metricas from "../pages/admin/Metricas";

vi.mock("../api/metricas", () => ({
  obtenerResumenDashboard: vi.fn(),
  obtenerSaludSistema: vi.fn(),
}));

vi.mock("../lib/toasts", () => ({
  toast: vi.fn(),
}));

import {
  obtenerResumenDashboard as mockedResumen,
  obtenerSaludSistema as mockedSalud,
} from "../api/metricas";
import { toast as mockedToast } from "../lib/toasts";

const mockedResumenFn = mockedResumen as ReturnType<typeof vi.fn>;
const mockedSaludFn = mockedSalud as ReturnType<typeof vi.fn>;

function renderMetricas() {
  return render(
    <MemoryRouter>
      <Metricas />
    </MemoryRouter>,
  );
}

const RESUMEN_OK = {
  total_consultas: 30,
  en_progreso: 2,
  completadas: 26,
  con_error: 3,
  por_tipo: [{ tipo_respuesta: "consulta_simple", cantidad: 20 }],
  por_modelo: [
    { modelo_llm: "llama3:8b", cantidad: 20, latencia_promedio_ms: 18598 },
  ],
  por_usuario: [
    {
      usuario_id: 32,
      usuario_carnet: "qasup",
      usuario_nombre: "QA Supervisor",
      cantidad: 22,
    },
  ],
  consultas_por_dia: [{ fecha: "2026-08-16", cantidad: 30 }],
  // Endpoint LLM local (Ollama); el reranker deshabilitado no muestra modelo.
  llm_endpoint: { id: "ollama_default", provider: "ollama", model: "llama3:8b" },
  embedding_endpoint: {
    id: "ollama_default",
    provider: "ollama",
    model: "nomic-embed-text",
  },
  reranker_endpoint: null,
};

const SALUD_OK = {
  postgres_ok: true,
  qdrant_ok: true,
  qdrant_puntos: 4774,
  sesiones_activas: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Dashboard admin (Metricas)", () => {
  it("muestra título y KPI cards con datos", async () => {
    mockedResumenFn.mockResolvedValue(RESUMEN_OK);
    mockedSaludFn.mockResolvedValue(SALUD_OK);
    renderMetricas();

    expect(
      await screen.findByRole("heading", { name: /dashboard/i }),
    ).toBeInTheDocument();
    // KPIs generales — "30" aparece en card + chart SVG, usar getAllByText.
    expect(screen.getAllByText("30").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Completadas")).toBeInTheDocument();
    expect(screen.getByText("En progreso")).toBeInTheDocument();
    expect(screen.getByText("Con error")).toBeInTheDocument();
  });

  it("muestra barra de salud con porcentajes", async () => {
    mockedResumenFn.mockResolvedValue(RESUMEN_OK);
    mockedSaludFn.mockResolvedValue(SALUD_OK);
    renderMetricas();

    // La leyenda de salud contiene "%" — buscar por eso para distinguir de la card.
    expect(await screen.findByText(/%\s*completadas/)).toBeInTheDocument();
    expect(screen.getByText(/%\s*con error/)).toBeInTheDocument();
    expect(screen.getByText(/%\s*en progreso/)).toBeInTheDocument();
  });

  it("muestra chart por día y secciones de distribución", async () => {
    mockedResumenFn.mockResolvedValue(RESUMEN_OK);
    mockedSaludFn.mockResolvedValue(SALUD_OK);
    renderMetricas();

    expect(
      await screen.findByLabelText(/consultas por día/i),
    ).toBeInTheDocument();
    // Configuración de modelos: sale de los endpoints activos, no de
    // valores fijos en el componente.
    expect(screen.getByText("Configuración de modelos")).toBeInTheDocument();
    const cardLlm = screen
      .getByText("LLM (generación)")
      .closest("div") as HTMLElement;
    expect(within(cardLlm).getByText("llama3:8b")).toBeInTheDocument();
    expect(within(cardLlm).getByText("Ollama (local)")).toBeInTheDocument();
    const cardEmbeddings = screen
      .getByText("Embeddings")
      .closest("div") as HTMLElement;
    expect(
      within(cardEmbeddings).getByText("Ollama (local)"),
    ).toBeInTheDocument();
    // Reranker sin configurar: ni modelo ni badge.
    const cardReranker = screen
      .getByText("Reranker")
      .closest("div") as HTMLElement;
    expect(
      within(cardReranker).getByText("No configurado"),
    ).toBeInTheDocument();
    expect(within(cardReranker).queryByText(/\(local\)|\(remoto\)/)).toBeNull();
    // Distribución de uso: sigue leyendo el modelo persistido por consulta.
    expect(screen.getAllByText("llama3:8b").length).toBeGreaterThanOrEqual(1);
    // Distribución de uso.
    expect(screen.getByText("Distribución de uso")).toBeInTheDocument();
    // Tipo de respuesta.
    expect(screen.getByText(/Consulta simple · 20/)).toBeInTheDocument();
    // Adopción por usuario.
    expect(screen.getByText("QA Supervisor (qasup)")).toBeInTheDocument();
  });

  it("estado vacío muestra mensaje de sin datos", async () => {
    mockedResumenFn.mockResolvedValue({
      ...RESUMEN_OK,
      total_consultas: 0,
      en_progreso: 0,
      completadas: 0,
      con_error: 0,
      por_tipo: [],
      por_modelo: [],
      por_usuario: [],
      consultas_por_dia: [],
    });
    mockedSaludFn.mockResolvedValue(null);
    renderMetricas();

    expect(
      await screen.findByText(/sin consultas en el período/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/distribución de uso/i)).not.toBeInTheDocument();
  });

  it("muestra error cuando la API falla", async () => {
    mockedResumenFn.mockRejectedValue(new Error("boom"));
    mockedSaludFn.mockResolvedValue(null);
    renderMetricas();

    await waitFor(() => {
      expect(mockedToast).toHaveBeenCalledWith(
        expect.stringContaining("No se pudieron cargar los datos"),
        "error",
      );
    });
  });

  it("muestra sección Infraestructura con estado de componentes", async () => {
    mockedResumenFn.mockResolvedValue(RESUMEN_OK);
    mockedSaludFn.mockResolvedValue(SALUD_OK);
    renderMetricas();

    expect(await screen.findByText("Infraestructura")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Qdrant (corpus jurídico)")).toBeInTheDocument();
    expect(screen.getByText("Operativo")).toBeInTheDocument();
    expect(screen.getByText(/puntos/)).toBeInTheDocument();
    expect(screen.getByText("Sala de Control")).toBeInTheDocument();
  });

  it("oculta sección Infraestructura si la consulta de salud falla", async () => {
    mockedResumenFn.mockResolvedValue(RESUMEN_OK);
    mockedSaludFn.mockRejectedValue(new Error("salud caida"));
    renderMetricas();

    await screen.findByRole("heading", { name: /dashboard/i });
    expect(screen.queryByText("Infraestructura")).not.toBeInTheDocument();
    // El fallo de salud es silencioso: no debe disparar toast propio.
    expect(mockedToast).not.toHaveBeenCalled();
  });
});
