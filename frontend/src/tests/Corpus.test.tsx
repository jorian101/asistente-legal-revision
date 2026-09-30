// Test Corpus: 3 tabs (Normas / Indexar / Segmentos), selector de embedding
// y navegación de fragmentos con DataTable.
//
// Mock del módulo api/corpus (mismo patrón previo). El tab por defecto es
// "Normas", así que los tests de upload/detección navegan a "Indexar" y los
// de fragmentos a "Segmentos".

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import Corpus from "../pages/admin/Corpus";
import { ToastContainer } from "../lib/toasts";

vi.mock("../api/corpus", () => ({
  listarNormas: vi.fn(),
  listarEndpointsEmbedding: vi.fn(),
  listarEndpointsLLM: vi.fn(),
  listarEndpointsReranker: vi.fn(),
  obtenerLLMSeleccionado: vi.fn(),
  obtenerRerankerSeleccionado: vi.fn(),
  seleccionarLLM: vi.fn(),
  seleccionarReranker: vi.fn(),
  obtenerNormalizarQuery: vi.fn(),
  setNormalizarQuery: vi.fn(),
  listarFragmentos: vi.fn(),
  indexarNorma: vi.fn(),
  reconciliarCorpus: vi.fn(),
  detectarPatrones: vi.fn(),
  editarNorma: vi.fn(),
  eliminarNorma: vi.fn(),
  // HU-23: umbrales del pipeline (tab Modelos).
  obtenerConfiguracionRAG: vi.fn().mockResolvedValue(null),
  ajustarParametrosRAG: vi.fn(),
}));
vi.mock("../api/jobs", () => ({
  obtenerTrabajo: vi.fn(),
  cancelarTrabajo: vi.fn(),
}));

import {
  detectarPatrones,
  eliminarNorma,
  indexarNorma,
  listarEndpointsEmbedding,
  listarEndpointsLLM,
  listarEndpointsReranker,
  listarFragmentos,
  listarNormas,
  obtenerLLMSeleccionado,
  obtenerNormalizarQuery,
  obtenerRerankerSeleccionado,
  reconciliarCorpus,
  seleccionarLLM,
  seleccionarReranker,
} from "../api/corpus";
import { obtenerTrabajo, cancelarTrabajo } from "../api/jobs";

const mockedListar = listarNormas as ReturnType<typeof vi.fn>;
const mockedDetectar = detectarPatrones as ReturnType<typeof vi.fn>;
const mockedIndexar = indexarNorma as ReturnType<typeof vi.fn>;
const mockedObtenerTrabajo = obtenerTrabajo as ReturnType<typeof vi.fn>;
const mockedCancelarTrabajo = cancelarTrabajo as ReturnType<typeof vi.fn>;
const mockedEndpoints = listarEndpointsEmbedding as ReturnType<typeof vi.fn>;
const mockedFragmentos = listarFragmentos as ReturnType<typeof vi.fn>;
const mockedReconciliar = reconciliarCorpus as ReturnType<typeof vi.fn>;
const mockedEliminar = eliminarNorma as ReturnType<typeof vi.fn>;
const mockedLLMEndpoints = listarEndpointsLLM as ReturnType<typeof vi.fn>;
const mockedRerankEndpoints = listarEndpointsReranker as ReturnType<
  typeof vi.fn
>;
const mockedLLMSel = obtenerLLMSeleccionado as ReturnType<typeof vi.fn>;
const mockedRerankSel = obtenerRerankerSeleccionado as ReturnType<typeof vi.fn>;
const mockedSelLLM = seleccionarLLM as ReturnType<typeof vi.fn>;
const mockedSelRerank = seleccionarReranker as ReturnType<typeof vi.fn>;
const obtenerNormalizarQueryMock = obtenerNormalizarQuery as ReturnType<
  typeof vi.fn
>;

function renderCorpus() {
  return render(
    <MemoryRouter>
      <Corpus />
      <ToastContainer />
    </MemoryRouter>,
  );
}

const NORMAS = [
  {
    norma_id: 1,
    abreviatura: "CPPM",
    nombre: "CODIGO DE PROCEDIMIENTO PENAL MILITAR",
    tipo: "codigo_militar",
    jerarquia: "militar",
    version: null,
    indexado: true,
    indexado_por: 1,
  },
  {
    norma_id: 2,
    abreviatura: "CPE",
    nombre: "CONSTITUCION DE LA PROVINCIA",
    tipo: "constitucion",
    jerarquia: "constitucion",
    version: "1994",
    indexado: false,
    indexado_por: null,
  },
];

const ENDPOINTS = [
  {
    id: "ollama_default",
    provider: "ollama",
    model: "nomic-embed-text",
    dim: 768,
  },
  {
    id: "ollama_alt",
    provider: "ollama",
    model: "bge-m3",
    dim: 1024,
  },
];

const FRAGMENTOS = [
  {
    id: 11,
    norma_id: 1,
    qdrant_point_id: "p-1",
    texto: "Articulo 1 - Procedimiento",
    padre_ref_key: "art.1",
    nivel_jerarquico: 4,
    tipo_chunk: "articulo_simple",
  },
];

async function irAlTab(nombre: string) {
  await userEvent.click(screen.getByRole("tab", { name: nombre }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedListar.mockResolvedValue(NORMAS);
  mockedEndpoints.mockResolvedValue(ENDPOINTS);
  mockedLLMEndpoints.mockResolvedValue([
    { id: "ollama_default", provider: "ollama", model: "llama3:8b" },
  ]);
  mockedRerankEndpoints.mockResolvedValue([
    { id: "reranker_default", provider: "http", model: "bge-reranker-v2-m3" },
  ]);
  mockedLLMSel.mockResolvedValue(null);
  mockedRerankSel.mockResolvedValue(null);
  obtenerNormalizarQueryMock.mockResolvedValue({ activado: true });
  mockedDetectar.mockResolvedValue({
    mejor: null,
    confianza: 0,
    candidatos: [],
    error: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Corpus: tabs", () => {
  it("ordenar por nombre recarga el listado con orden=nombre", async () => {
    renderCorpus();

    await userEvent.selectOptions(
      screen.getByLabelText("Ordenar por"),
      "nombre",
    );

    await waitFor(() =>
      expect(mockedListar).toHaveBeenLastCalledWith("nombre"),
    );
  });

  it("muestra las 3 pestañas y por defecto la de Normas", async () => {
    renderCorpus();

    expect(screen.getByRole("tab", { name: "Normas" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Indexar" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Segmentos" })).toBeInTheDocument();

    // Tab Normas activo por defecto: muestra el listado.
    expect(
      await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR"),
    ).toBeInTheDocument();
  });

  it("cambia al tab Indexar y muestra el selector de embedding", async () => {
    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");

    await irAlTab("Indexar");

    const select = await screen.findByLabelText(/modelo de embedding/i);
    expect(select).toBeInstanceOf(HTMLSelectElement);
    expect(
      within(select as HTMLElement).getByText(
        /nomic-embed-text \(ollama, 768 dims\)/i,
      ),
    ).toBeInTheDocument();
  });

  it("cambia al tab Segmentos y navega fragmentos con filtros", async () => {
    mockedFragmentos.mockResolvedValue({
      items: FRAGMENTOS,
      total: 1,
      pagina: 1,
      por_pagina: 10,
    });

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");

    await irAlTab("Segmentos");

    expect(await screen.findByText(/procedimiento/i)).toBeInTheDocument();

    // Filtros presentes y envían norma_id al api.
    await userEvent.click(
      screen.getByRole("button", { name: "Todas", description: "Norma" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: /filtrar por norma/i,
    });
    await userEvent.click(
      within(dialogo).getByRole("button", { name: /CPPM/ }),
    );
    await waitFor(() => {
      expect(mockedFragmentos).toHaveBeenLastCalledWith(
        expect.objectContaining({ norma_id: 1 }),
      );
    });
  });

  it("tab Modelos muestra selectores y aplica LLM y reranker", async () => {
    const user = userEvent.setup();
    mockedSelLLM.mockResolvedValue({
      id: "ollama_default",
      provider: "ollama",
      model: "llama3:8b",
    });
    mockedSelRerank.mockResolvedValue({
      id: "reranker_default",
      provider: "http",
      model: "bge-reranker-v2-m3",
    });

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");
    await irAlTab("Modelos");

    expect(await screen.findByLabelText(/modelo de llm/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/modelo de reranker/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /aplicar llm/i }));
    await waitFor(() => {
      expect(mockedSelLLM).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: /aplicar reranker/i }));
    await waitFor(() => {
      expect(mockedSelRerank).toHaveBeenCalled();
    });
  });

  it("tab Segmentos con estado vacío", async () => {
    mockedFragmentos.mockResolvedValue({
      items: [],
      total: 0,
      pagina: 1,
      por_pagina: 10,
    });

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");

    await irAlTab("Segmentos");

    expect(await screen.findByText(/no hay segmentos/i)).toBeInTheDocument();
  });
});

describe("Corpus: Indexar", () => {
  it("detección: al elegir archivo detecta patrón y pre-selecciona el select", async () => {
    const user = userEvent.setup();
    const file = new File(["x"], "cpm.pdf", { type: "application/pdf" });
    mockedDetectar.mockResolvedValue({
      mejor: "CPE",
      confianza: 0.87,
      candidatos: [
        { abreviatura: "CPE", articulos_matcheados: 34, confianza: 0.87 },
        { abreviatura: "CPPM", articulos_matcheados: 2, confianza: 0.1 },
      ],
      error: null,
    });

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");
    await irAlTab("Indexar");
    await screen.findByLabelText(/modelo de embedding/i);

    const input = screen.getByLabelText(/pdf \/ docx/i);
    await user.upload(input, file);

    expect(await screen.findByText(/patrón detectado/i)).toBeInTheDocument();

    const select = screen.getByLabelText(/abreviatura/i) as HTMLSelectElement;
    await waitFor(() => {
      expect(select.value).toBe("CPE");
    });
  });

  it("upload: encola el indexado y muestra el resultado al terminar", async () => {
    const user = userEvent.setup();
    const file = new File(["x"], "cppm.pdf", { type: "application/pdf" });
    mockedIndexar.mockResolvedValue({ job_id: "j1", estado: "en_curso" });
    mockedObtenerTrabajo.mockResolvedValue({
      id: "j1",
      tipo: "norma",
      estado: "completado",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: "2026-09-22T00:00:05Z",
      error: null,
      resultado: {
        norma_id: 1,
        fragmentos_creados: 42,
        vectores_indexados: 42,
        qdrant_collection: "corpus_juridico",
      },
    });

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");
    await irAlTab("Indexar");
    await screen.findByLabelText(/modelo de embedding/i);

    await user.selectOptions(screen.getByLabelText(/abreviatura/i), "CPPM");
    await user.upload(screen.getByLabelText(/pdf \/ docx/i), file);
    await user.click(screen.getByRole("button", { name: /subir e indexar/i }));

    await waitFor(() => {
      expect(mockedIndexar).toHaveBeenCalledWith(
        "CPPM",
        file,
        undefined,
        "ollama_default",
        expect.any(Function),
      );
    });
    expect(
      await screen.findByText(/42 fragmentos, 42 vectores/i),
    ).toBeInTheDocument();
  });

  it("indexado en curso: se puede cancelar", async () => {
    const user = userEvent.setup();
    const file = new File(["x"], "cppm.pdf", { type: "application/pdf" });
    mockedIndexar.mockResolvedValue({ job_id: "j2", estado: "en_curso" });
    // El test solo cubre hasta pedir la cancelación: no espera el próximo
    // poll (1500ms), que ya está cubierto por Fuentes.test.tsx.
    mockedObtenerTrabajo.mockResolvedValue({
      id: "j2",
      tipo: "norma",
      estado: "en_curso",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: null,
      error: null,
      resultado: null,
    });
    mockedCancelarTrabajo.mockResolvedValue({});

    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");
    await irAlTab("Indexar");
    await screen.findByLabelText(/modelo de embedding/i);

    await user.selectOptions(screen.getByLabelText(/abreviatura/i), "CPPM");
    await user.upload(screen.getByLabelText(/pdf \/ docx/i), file);
    await user.click(screen.getByRole("button", { name: /subir e indexar/i }));

    await user.click(
      await screen.findByRole("button", { name: "Cancelar indexado" }),
    );
    await waitFor(() =>
      expect(mockedCancelarTrabajo).toHaveBeenCalledWith("j2"),
    );
  });
});

describe("Corpus: reconciliación con ConfirmDialog", () => {
  it("reconciliar requiere confirmación y cancela no ejecuta", async () => {
    const user = userEvent.setup();
    mockedReconciliar.mockResolvedValue({
      pg_count: 5,
      qdrant_count: 4,
      huerfanos_eliminados: 1,
    });
    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");

    await user.click(
      screen.getByRole("button", { name: /sincronizar índice de búsqueda/i }),
    );

    // Diálogo visible; cancelar no llama a la API.
    expect(
      screen.getByRole("dialog", { name: /sincronizar índice de búsqueda/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^cancelar$/i }));
    expect(mockedReconciliar).not.toHaveBeenCalled();

    // Abrir de nuevo y confirmar → llama a la API y cierra el diálogo.
    await user.click(
      screen.getByRole("button", { name: /sincronizar índice de búsqueda/i }),
    );
    await user.click(screen.getByRole("button", { name: /^sincronizar$/i }));

    await waitFor(() => {
      expect(mockedReconciliar).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/sincronización:/i)).toBeInTheDocument();
  });
});

describe("Corpus: eliminar norma con ConfirmDialog", () => {
  it("eliminar requiere confirmación, cancela no ejecuta y recarga al confirmar", async () => {
    const user = userEvent.setup();
    mockedEliminar.mockResolvedValue(undefined);
    renderCorpus();
    await screen.findByText("CODIGO DE PROCEDIMIENTO PENAL MILITAR");

    await user.click(screen.getByRole("button", { name: "Eliminar CPPM" }));

    const dialogo = screen.getByRole("dialog", { name: /eliminar norma/i });
    expect(dialogo).toBeInTheDocument();

    // Cancelar no llama a la API.
    await user.click(
      within(dialogo).getByRole("button", { name: /^cancelar$/i }),
    );
    expect(mockedEliminar).not.toHaveBeenCalled();

    // Confirmar → llama con el norma_id de la fila, cierra y recarga.
    await user.click(screen.getByRole("button", { name: "Eliminar CPPM" }));
    await user.click(
      within(screen.getByRole("dialog", { name: /eliminar norma/i })).getByRole(
        "button",
        { name: /^eliminar$/i },
      ),
    );

    await waitFor(() => {
      expect(mockedEliminar).toHaveBeenCalledWith(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/norma eliminada/i)).toBeInTheDocument();
    await waitFor(() => expect(mockedListar).toHaveBeenCalledTimes(2));
  });
});
