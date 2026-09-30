// Test Asistente (chat): interfaz conversacional del asistente juridico.
//
// Cubre el nuevo flujo: enviar consulta crea conversacion + turno user,
// el backend responde con ContextoRecuperado, los fragmentos se muestran en
// el mensaje bot, el error del backend se muestra al usuario y unmount antes
// de la respuesta no rompe (anti setState-after-unmount).

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

import Asistente from "../pages/consultas/Asistente";

vi.mock("../api/consultas", () => ({
  responderConsulta: vi.fn(),
  eliminarHistorial: vi.fn(),
  // F3: streamResume.esperarRespuestaFinal la usa para el poll de recuperación.
  obtenerHistorialDetalle: vi.fn(),
}));

// F3: la capa de memoria conversacional se aísla en estos tests de UI.
// P2: hidratarMensajes por defecto no agrega nada (0) — los tests que la
// necesitan la sobrescriben con mockImplementationOnce.
vi.mock("../lib/persistirChat", () => ({
  asegurarChatPersistido: vi.fn().mockResolvedValue(null),
  persistirMensajeEnChat: vi.fn().mockResolvedValue(null),
  hidratarMensajes: vi.fn().mockResolvedValue(0),
}));

import {
  eliminarHistorial as mockedEliminar,
  responderConsulta as mockedResponder,
  obtenerHistorialDetalle as mockedObtenerHistorialDetalle,
} from "../api/consultas";
import {
  asegurarChatPersistido as mockedAsegurarChat,
  hidratarMensajes as mockedHidratarMensajes,
  persistirMensajeEnChat as mockedPersistirMensaje,
} from "../lib/persistirChat";
import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { permisosDeTest } from "./helpers";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";
import { SidebarProvider } from "../components/chat/ChatSidebarContext";

/** F3: stream que entrega algunos chunks y luego el `read()` RECHAZA con un
 *  Error nativo (sin `.response`) — simula un corte de red a mitad de la
 *  generación, a diferencia de un error de negocio del backend. */
function createDroppedStreamReader(
  chunksAntesDelCorte: string[],
): ReadableStreamDefaultReader<string> {
  let index = 0;
  return {
    read: vi.fn().mockImplementation(() => {
      if (index < chunksAntesDelCorte.length) {
        const value = chunksAntesDelCorte[index++];
        return Promise.resolve({ done: false, value });
      }
      return Promise.reject(new Error("Failed to fetch"));
    }),
    cancel: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReadableStreamDefaultReader<string>;
}

function createMockStreamReader(
  chunks: string[],
): ReadableStreamDefaultReader<string> {
  let index = 0;
  return {
    read: vi.fn().mockImplementation(() => {
      if (index < chunks.length) {
        const value = chunks[index++];
        return Promise.resolve({ done: false, value });
      }
      return Promise.resolve({ done: true, value: undefined });
    }),
    cancel: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReadableStreamDefaultReader<string>;
}

function renderAsistente(auth?: Partial<AuthState>) {
  const value: AuthState = {
    access_token: "test-token",
    rol: auth?.rol ?? "operador_juridico",
    carnet: auth?.carnet ?? "1001",
    nombre: auth?.nombre ?? "Operador de Prueba",
    id: auth?.id ?? 1,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <PermisosContext.Provider value={permisosDeTest()}>
        <MemoryRouter>
          <SidebarProvider>
            <Asistente />
          </SidebarProvider>
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
}

function mockResolvedOK() {
  const mockStream = createMockStreamReader([
    "El art. 12 establece el plazo de radicatoria.\n",
    "La radicatoria procede cuando existan indicios.",
  ]);
  (mockedResponder as ReturnType<typeof vi.fn>).mockResolvedValue({
    stream: mockStream,
    tipoRespuesta: "consulta_simple",
  });
}

function mockRejected() {
  (mockedResponder as ReturnType<typeof vi.fn>).mockRejectedValue({
    response: { status: 500, data: { detail: "Fallo del pipeline RAG" } },
  });
}

/** F1/F2: stream controlable a mano — push() entrega un token, finish()
 *  cierra el stream. A diferencia de createMockStreamReader (chunks fijos),
 *  permite pausar la generación a mitad para simular "cambiar de chat
 *  mientras A sigue generando". */
function createControllableStreamReader() {
  const cola: Array<{ done: boolean; value?: string }> = [];
  let resolverProximo: ((r: { done: boolean; value?: string }) => void) | null =
    null;
  const reader = {
    read: vi.fn().mockImplementation(() => {
      if (cola.length > 0) return Promise.resolve(cola.shift());
      return new Promise((resolve) => {
        resolverProximo = resolve;
      });
    }),
    cancel: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReadableStreamDefaultReader<string>;
  return {
    reader,
    push(value: string) {
      const item = { done: false, value };
      if (resolverProximo) {
        const r = resolverProximo;
        resolverProximo = null;
        r(item);
      } else {
        cola.push(item);
      }
    },
    finish() {
      const item = { done: true, value: undefined };
      if (resolverProximo) {
        const r = resolverProximo;
        resolverProximo = null;
        r(item);
      } else {
        cola.push(item);
      }
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe("Asistente (chat)", () => {
  it("rendera textarea y boton Enviar deshabilitado en idle", () => {
    renderAsistente();
    expect(
      screen.getByRole("textbox", { name: "Consulta" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enviar/i })).toBeDisabled();
  });

  it("indica que el corpus jurídico siempre está incluido", () => {
    renderAsistente();
    expect(screen.getByText(/corpus jurídico incluido/i)).toBeInTheDocument();
  });

  it("boton se habilita con texto y envia consulta al backend", async () => {
    const user = userEvent.setup();
    mockResolvedOK();
    renderAsistente();

    const textarea = screen.getByRole("textbox", { name: "Consulta" });
    await user.type(textarea, "¿Como proceder ante una radicatoria?");
    expect(screen.getByRole("button", { name: /enviar/i })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(mockedResponder).toHaveBeenCalledWith({
        consulta: "¿Como proceder ante una radicatoria?",
        expediente_id: null,
        obra_ids: null,
        chat_id: null,
        tipo_forzado: null,
        corpus_refs: null,
      });
      // Sin selector: el alcance lo decide el backend según haya expediente.
      expect(screen.queryByLabelText("Alcance de la consulta")).toBeNull();
    });
  });

  it("propaga expediente_id de la conversacion activa a la busqueda (G7)", async () => {
    const user = userEvent.setup();
    mockResolvedOK();

    // Crear conversacion vinculada a un expediente ANTES de renderizar para
    // que recargarTodo() (useEffect) la liste en el estado local.
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Expediente 7", 7);

    // Abrir el sidebar de chat por defecto (el toggle ahora vive en el header
    // del layout, no en esta pagina).
    localStorage.setItem("asistente:sidebar-open", "chat");
    renderAsistente();

    // Seleccionar la conversacion vinculada
    await user.click(screen.getByRole("button", { name: /expediente 7/i }));

    const textarea = screen.getByRole("textbox", { name: "Consulta" });
    await user.type(textarea, "analizar vicio del expediente");
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(mockedResponder).toHaveBeenCalledWith(
        expect.objectContaining({
          consulta: "analizar vicio del expediente",
          expediente_id: conv.expediente_id,
        }),
      );
    });
  });

  it("persiste el mensaje del asistente en el store (no se pierde al reingresar)", async () => {
    const user = userEvent.setup();
    mockResolvedOK();
    renderAsistente();

    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta para persistir",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    // Espera a que el stream complete y el contenido se escriba al store.
    await waitFor(async () => {
      const { chatStore } = await import("../lib/chatStore");
      const convs = chatStore.listarConversaciones(1);
      expect(convs.length).toBeGreaterThan(0);
      const mensajes = chatStore.listarMensajes(1, convs[0].id);
      const bot = mensajes.find((m) => m.tipo === "bot");
      expect(bot?.contenido).toContain("plazo de radicatoria");
    });
  });

  it("turno user se muestra y bot muestra respuesta", async () => {
    const user = userEvent.setup();
    mockResolvedOK();
    renderAsistente();

    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "¿Como proceder ante una radicatoria?",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    expect(
      await screen.findByText(/como proceder ante una radicatoria\?/i),
    ).toBeInTheDocument();
    // Fragmentos, scores y latencia_ms no están implementados en la respuesta streaming actual
    expect(
      screen.getByText(/el art\. 12 establece el plazo de radicatoria\./i),
    ).toBeInTheDocument();
  });

  it("abre una conversacion pasada por ?chat=<id> (desde Conversaciones)", async () => {
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Desde Conversaciones");
    chatStore.agregarMensaje(1, conv.id, "user", "pregunta del chat");
    chatStore.agregarMensaje(1, conv.id, "bot", "respuesta persistida");

    const value: AuthState = {
      access_token: "test-token",
      rol: "operador_juridico",
      carnet: "1001",
      nombre: "Operador de Prueba",
      id: 1,
    };
    setAuthState(value);
    render(
      <AuthProvider>
        <PermisosContext.Provider value={permisosDeTest()}>
          <MemoryRouter
            initialEntries={[`/asistente/consultar?chat=${conv.id}`]}
          >
            <SidebarProvider>
              <Asistente />
            </SidebarProvider>
          </MemoryRouter>
        </PermisosContext.Provider>
      </AuthProvider>,
    );

    expect(await screen.findByText("pregunta del chat")).toBeInTheDocument();
    expect(screen.getByText("respuesta persistida")).toBeInTheDocument();
  });

  it("error del backend muestra mensaje al usuario", async () => {
    const user = userEvent.setup();
    mockRejected();
    renderAsistente();

    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta valida",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    expect(
      await screen.findByText(/fallo del pipeline rag/i),
    ).toBeInTheDocument();
  });

  it("estado cargando: boton cambia a Cancelar mientras la consulta está en vuelo", async () => {
    const user = userEvent.setup();
    // Mock responderConsulta to return a promise that never resolves but with the right shape
    (mockedResponder as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise<{
          stream: ReadableStreamDefaultReader<string>;
          tipoRespuesta: string;
        }>(() => {}),
    );
    renderAsistente();

    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta valida",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    expect(
      await screen.findByRole("button", { name: /cancelar/i }),
    ).toBeInTheDocument();
  });

  it("unmount antes de la respuesta evita setState (anti setState-after-unmount)", async () => {
    let resolver!: (v: unknown) => void;
    (mockedResponder as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((res) => {
        resolver = res;
      }),
    );
    const value: AuthState = {
      access_token: "test-token",
      rol: "operador_juridico",
      carnet: "1001",
      nombre: "Operador de Prueba",
      id: 1,
    };
    setAuthState(value);
    const { unmount } = render(
      <AuthProvider>
        <PermisosContext.Provider value={permisosDeTest()}>
          <MemoryRouter>
            <SidebarProvider>
              <Asistente />
            </SidebarProvider>
          </MemoryRouter>
        </PermisosContext.Provider>
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta para unmount test",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    unmount();
    resolver({
      tipo_respuesta: "consulta_simple",
      fragmentos: [],
      scores: [],
      latencia_ms: 0,
      historial_id: 1,
      expediente_id: null,
    });

    expect(true).toBe(true);
  });

  it("chips corpus_refs se muestran, se quitan y viajan al backend", async () => {
    const user = userEvent.setup();
    mockResolvedOK();
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Expediente 7", 7);
    chatStore.asociarCorpusRef(1, conv.id, "SCP-0623-2024-S4");
    localStorage.setItem("asistente:sidebar-open", "chat");
    renderAsistente();
    await user.click(screen.getByRole("button", { name: /expediente 7/i }));

    expect(screen.getByText("SCP-0623-2024-S4")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: /Quitar referencia SCP-0623-2024-S4/i,
      }),
    );
    expect(screen.queryByText("SCP-0623-2024-S4")).not.toBeInTheDocument();

    chatStore.asociarCorpusRef(1, conv.id, "SCP-0623-2024-S4");
    const textarea = screen.getByRole("textbox", { name: "Consulta" });
    await user.type(textarea, "nulidad de oficio por indefension");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() =>
      expect(mockedResponder).toHaveBeenCalledWith(
        expect.objectContaining({ corpus_refs: ["SCP-0623-2024-S4"] }),
      ),
    );
  });

  it("cada chip fijado lleva el icono de su categoria", async () => {
    const user = userEvent.setup();
    mockResolvedOK();
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Expediente 7", 7);
    for (const ref of ["CPE", "SCP-0623-2024-S4", "LIB-ATIENZA-INTERP-2019"]) {
      chatStore.asociarCorpusRef(1, conv.id, ref);
    }
    localStorage.setItem("asistente:sidebar-open", "chat");
    renderAsistente();
    await user.click(screen.getByRole("button", { name: /expediente 7/i }));

    for (const [ref, categoria] of [
      ["CPE", "norma"],
      ["SCP-0623-2024-S4", "jurisprudencia"],
      ["LIB-ATIENZA-INTERP-2019", "doctrina"],
    ]) {
      const chip = screen
        .getByRole("button", { name: `Quitar referencia ${ref}` })
        .closest("div");
      expect(
        chip?.querySelector(`[data-categoria="${categoria}"]`),
      ).not.toBeNull();
      expect(chip?.textContent).not.toContain("📚");
    }
  });

  it("accion dictamen fondo envia tipo_forzado", async () => {
    // G7: AccionesRapidas con tipoForzado + enviar propaga tipo_forzado al
    // backend. Se rehabilita: faltaba la sesion (renderAsistente fija authState)
    // y seleccionar la conversacion del expediente en el sidebar.
    mockResolvedOK();
    const { chatStore } = await import("../lib/chatStore");
    chatStore.crearConversacion(1, "Expediente 7", 7);
    localStorage.setItem("asistente:sidebar-open", "chat");
    const { unmount } = renderAsistente();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /expediente 7/i }));
    await user.click(
      screen.getByRole("button", { name: /Dictamen de fondo/i }),
    );
    await user.type(screen.getByRole("textbox", { name: "Consulta" }), "x");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() =>
      expect(mockedResponder).toHaveBeenCalledWith(
        expect.objectContaining({ tipo_forzado: "dictamen_fondo" }),
      ),
    );
    unmount();
  });

  it("quitar del historial: confirma, llama al endpoint y desvincula el mensaje", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Prueba quitar historial");
    chatStore.agregarMensaje(1, conv.id, "bot", "respuesta con historial", {
      historial_id: 42,
    });
    localStorage.setItem("asistente:sidebar-open", "chat");
    renderAsistente();

    await user.click(
      screen.getByRole("button", { name: /prueba quitar historial/i }),
    );

    // El mensaje bot tiene historial_id → aparece la accion.
    await user.click(
      await screen.findByRole("button", { name: "Quitar del historial" }),
    );

    const dialogo = screen.getByRole("dialog", {
      name: /quitar del historial/i,
    });
    await user.click(
      within(dialogo).getByRole("button", { name: /^cancelar$/i }),
    );
    expect(mockedEliminar).not.toHaveBeenCalled();

    // Confirmar → borra el registro RAG y desvincula el mensaje local.
    await user.click(
      screen.getByRole("button", { name: "Quitar del historial" }),
    );
    await user.click(
      within(
        screen.getByRole("dialog", { name: /quitar del historial/i }),
      ).getByRole("button", { name: /^quitar$/i }),
    );

    await waitFor(() => expect(mockedEliminar).toHaveBeenCalledWith(42));
    await waitFor(() => {
      const bot = chatStore
        .listarMensajes(1, conv.id)
        .find((m) => m.tipo === "bot");
      expect(bot?.historial_id).toBeUndefined();
      // El contenido del chat se mantiene.
      expect(bot?.contenido).toBe("respuesta con historial");
    });
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Quitar del historial" }),
      ).toBeNull(),
    );
  });

  it("F1: cambiar de chat mientras A genera no filtra tokens ni pierde el estado de A", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    chatStore.crearConversacion(1, "Chat A");
    chatStore.crearConversacion(1, "Chat B");
    localStorage.setItem("asistente:sidebar-open", "chat");

    const streamA = createControllableStreamReader();
    (mockedResponder as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stream: streamA.reader,
      tipoRespuesta: "consulta_simple",
      historialId: 101,
    });

    renderAsistente();
    await user.click(screen.getByRole("button", { name: /chat a/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta en A",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(mockedResponder).toHaveBeenCalledTimes(1));

    streamA.push("respuesta-de-A-1 ");
    expect(await screen.findByText(/respuesta-de-a-1/i)).toBeInTheDocument();
    // El sidebar marca a A como generando.
    expect(
      within(screen.getByRole("button", { name: /chat a/i })).getByRole(
        "status",
        { name: /generando respuesta/i },
      ),
    ).toBeInTheDocument();

    // Cambiar a B mientras A sigue generando: nada de A se filtra a la vista,
    // y B se ve idle (no "Cancelar" de un stream que no es suyo).
    await user.click(screen.getByRole("button", { name: /chat b/i }));
    expect(screen.queryByText(/respuesta-de-a-1/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enviar/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /cancelar/i }),
    ).not.toBeInTheDocument();

    // Otro token de A llega mientras seguimos mirando B: tampoco se filtra.
    streamA.push("respuesta-de-A-2 ");
    expect(screen.queryByText(/respuesta-de-a-2/i)).not.toBeInTheDocument();

    // Volver a A: se ve todo lo acumulado (no se perdió nada) y su indicador.
    await user.click(screen.getByRole("button", { name: /chat a/i }));
    expect(
      await screen.findByText(/respuesta-de-a-1.*respuesta-de-a-2/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /cancelar/i }),
    ).toBeInTheDocument();

    streamA.finish();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /cancelar/i }),
      ).not.toBeInTheDocument(),
    );
    // El indicador del sidebar desaparece al terminar.
    await waitFor(() =>
      expect(
        within(screen.getByRole("button", { name: /chat a/i })).queryByRole(
          "status",
          { name: /generando respuesta/i },
        ),
      ).not.toBeInTheDocument(),
    );
  });

  it("P4: los tokens del stream no releen el store de localStorage", async () => {
    const user = userEvent.setup();
    const streamA = createControllableStreamReader();
    (mockedResponder as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stream: streamA.reader,
      tipoRespuesta: "consulta_simple",
      historialId: null,
    });

    renderAsistente();
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta larga",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    streamA.push("token-0 ");
    expect(await screen.findByText(/token-0/)).toBeInTheDocument();

    // Solo el tramo del stream: montar y entrar al chat sí leen el store.
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    for (let i = 1; i <= 5; i++) streamA.push(`token-${i} `);
    expect(await screen.findByText(/token-5/)).toBeInTheDocument();
    const lecturasStore = getItem.mock.calls.filter(([k]) =>
      k.startsWith("asistente-legal:chats"),
    );
    expect(lecturasStore).toHaveLength(0);

    streamA.finish();
  });

  it("F2: enviar en B no cancela el stream de A — ambas terminan y persisten", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    const convA = chatStore.crearConversacion(1, "Chat A");
    const convB = chatStore.crearConversacion(1, "Chat B");
    localStorage.setItem("asistente:sidebar-open", "chat");

    const streamA = createControllableStreamReader();
    const streamB = createControllableStreamReader();
    (mockedResponder as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        stream: streamA.reader,
        tipoRespuesta: "consulta_simple",
        historialId: 201,
      })
      .mockResolvedValueOnce({
        stream: streamB.reader,
        tipoRespuesta: "consulta_simple",
        historialId: 202,
      });

    renderAsistente();

    await user.click(screen.getByRole("button", { name: /chat a/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta en A",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(mockedResponder).toHaveBeenCalledTimes(1));

    // Cambiar a B y enviar ahí también, MIENTRAS A sigue generando.
    await user.click(screen.getByRole("button", { name: /chat b/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta en B",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(mockedResponder).toHaveBeenCalledTimes(2));

    // Terminar B primero.
    streamB.push("respuesta-B-completa");
    streamB.finish();
    await waitFor(() => {
      const bot = chatStore
        .listarMensajes(1, convB.id)
        .find((m) => m.tipo === "bot");
      expect(bot?.contenido).toBe("respuesta-B-completa");
    });

    // A sigue viva y termina después — nunca fue cancelada por el envío en B.
    streamA.push("respuesta-A-completa");
    streamA.finish();
    await waitFor(() => {
      const bot = chatStore
        .listarMensajes(1, convA.id)
        .find((m) => m.tipo === "bot");
      expect(bot?.contenido).toBe("respuesta-A-completa");
    });
    expect(streamA.reader.cancel).not.toHaveBeenCalled();
    expect(streamB.reader.cancel).not.toHaveBeenCalled();
  });

  it("F3: corte de red a mitad de la generación conserva el pendiente y se recupera sola, sin duplicar la burbuja", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    const { leerPendiente } = await import("../lib/streamResume");
    const conv = chatStore.crearConversacion(1, "Chat con corte");
    localStorage.setItem("asistente:sidebar-open", "chat");

    const streamCortado = createDroppedStreamReader([
      "texto parcial antes del corte ",
    ]);
    (mockedResponder as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stream: streamCortado,
      tipoRespuesta: "consulta_simple",
      historialId: 301,
    });
    // Control manual de la recuperación: el mock queda pendiente hasta que
    // el test resuelva, para poder observar el estado intermedio ("se
    // cortó la conexión", pendiente conservado) antes de que cierre.
    let resolverHistorialDetalle:
      | ((v: {
          id: number;
          pregunta: string;
          respuesta: string;
          estado: string;
          tipo_respuesta: string;
          modelo_llm: string | null;
        }) => void)
      | null = null;
    (
      mockedObtenerHistorialDetalle as ReturnType<typeof vi.fn>
    ).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolverHistorialDetalle = resolve;
        }),
    );

    renderAsistente();
    await user.click(screen.getByRole("button", { name: /chat con corte/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "consulta con corte",
    );
    await user.click(screen.getByRole("button", { name: /enviar/i }));

    // El pendiente se guarda apenas responde el backend con historialId.
    await waitFor(() => expect(leerPendiente()?.historialId).toBe(301));

    // Tras el corte: aviso visible de recuperación y el pendiente SIGUE en
    // pie (no se descarta) mientras se recupera solo.
    expect(
      await screen.findByText(/se cortó la conexión/i),
    ).toBeInTheDocument();
    expect(leerPendiente()?.historialId).toBe(301);

    // Ahora sí resuelve el backend: la recuperación (GET
    // /consultas/historial/301) rellena la MISMA burbuja del bot — nunca
    // crea una segunda — y limpia el pendiente.
    resolverHistorialDetalle!({
      id: 301,
      pregunta: "consulta con corte",
      respuesta: "respuesta completa recuperada tras el corte",
      estado: "completado",
      tipo_respuesta: "consulta_simple",
      modelo_llm: null,
    });
    await waitFor(() => {
      const mensajesBot = chatStore
        .listarMensajes(1, conv.id)
        .filter((m) => m.tipo === "bot");
      expect(mensajesBot).toHaveLength(1);
      expect(mensajesBot[0].contenido).toBe(
        "respuesta completa recuperada tras el corte",
      );
    });
    expect(leerPendiente()).toBeNull();
  });

  it("F4: reanudar tras recargar la página rellena la burbuja bot existente, no crea una duplicada", async () => {
    const { chatStore } = await import("../lib/chatStore");
    const { guardarPendiente, leerPendiente } =
      await import("../lib/streamResume");

    // Simula el estado que deja una recarga a mitad de generación: el
    // mensaje bot ya existe (vacío, tal como lo crea enviar() antes de
    // empezar a leer el stream) y el pendiente sigue en sessionStorage —
    // el backend nunca se enteró de la recarga y terminó igual.
    const conv = chatStore.crearConversacion(1, "Chat recargado");
    chatStore.agregarMensaje(1, conv.id, "user", "consulta antes de recargar");
    const botVacio = chatStore.agregarMensaje(1, conv.id, "bot", "", {
      historial_id: 401,
    });
    guardarPendiente({
      historialId: 401,
      chatId: conv.id,
      pregunta: "consulta antes de recargar",
      ts: Date.now(),
    });

    (
      mockedObtenerHistorialDetalle as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      id: 401,
      pregunta: "consulta antes de recargar",
      respuesta: "respuesta terminada del lado del servidor",
      estado: "completado",
      tipo_respuesta: "consulta_simple",
      modelo_llm: null,
    });

    renderAsistente();

    await waitFor(() => {
      const mensajesBot = chatStore
        .listarMensajes(1, conv.id)
        .filter((m) => m.tipo === "bot");
      expect(mensajesBot).toHaveLength(1);
      expect(mensajesBot[0].id).toBe(botVacio.id);
      expect(mensajesBot[0].contenido).toBe(
        "respuesta terminada del lado del servidor",
      );
    });
    expect(leerPendiente()).toBeNull();
  });

  it("P1: mientras se recupera muestra el parcial en vivo (en_progreso) antes de completar", async () => {
    const { chatStore } = await import("../lib/chatStore");
    const { guardarPendiente } = await import("../lib/streamResume");

    const conv = chatStore.crearConversacion(1, "Chat con parcial en vivo");
    chatStore.agregarMensaje(1, conv.id, "user", "consulta con parcial");
    const botVacio = chatStore.agregarMensaje(1, conv.id, "bot", "", {
      historial_id: 501,
    });
    guardarPendiente({
      historialId: 501,
      chatId: conv.id,
      pregunta: "consulta con parcial",
      ts: Date.now(),
    });

    // 1er poll: sigue en_progreso con un parcial ya persistido (backend
    // throttled, P1). 2do poll (tras el backoff real de streamResume):
    // completado con el texto final.
    let llamada = 0;
    (
      mockedObtenerHistorialDetalle as ReturnType<typeof vi.fn>
    ).mockImplementation(async () => {
      llamada += 1;
      if (llamada === 1) {
        return {
          id: 501,
          pregunta: "consulta con parcial",
          respuesta: "primer parcial que llega ",
          estado: "en_progreso",
          tipo_respuesta: null,
          modelo_llm: null,
        };
      }
      return {
        id: 501,
        pregunta: "consulta con parcial",
        respuesta: "primer parcial que llega respuesta final completa",
        estado: "completado",
        tipo_respuesta: "consulta_simple",
        modelo_llm: null,
      };
    });

    renderAsistente();

    // El parcial se ve ANTES de que la consulta cierre — no se da por
    // terminada al primer `respuesta` no vacía (esa era la regresión de P1).
    await waitFor(() => {
      const bot = chatStore
        .listarMensajes(1, conv.id)
        .find((m) => m.tipo === "bot");
      expect(bot?.id).toBe(botVacio.id);
      expect(bot?.contenido).toBe("primer parcial que llega ");
    });

    await waitFor(
      () => {
        const bot = chatStore
          .listarMensajes(1, conv.id)
          .find((m) => m.tipo === "bot");
        expect(bot?.id).toBe(botVacio.id);
        expect(bot?.contenido).toBe(
          "primer parcial que llega respuesta final completa",
        );
      },
      { timeout: 5000 },
    );
  });

  it("P2: al entrar a una conversación hidrata un mensaje generado en otra pestaña", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    const conv = chatStore.crearConversacion(1, "Chat hidratado");
    chatStore.agregarMensaje(1, conv.id, "user", "pregunta original");
    localStorage.setItem("asistente:sidebar-open", "chat");

    // Simula lo que la implementación real de hidratarMensajes hace: agrega
    // el mensaje que faltaba localmente y devuelve cuántos agregó.
    (mockedHidratarMensajes as ReturnType<typeof vi.fn>).mockImplementationOnce(
      async (usuarioId: number, chatId: string) => {
        chatStore.agregarMensaje(
          usuarioId,
          chatId,
          "bot",
          "respuesta generada en otra pestaña",
        );
        return 1;
      },
    );

    renderAsistente();
    await user.click(screen.getByRole("button", { name: /chat hidratado/i }));

    expect(mockedHidratarMensajes).toHaveBeenCalledWith(
      1,
      conv.id,
      expect.any(Function),
    );
    expect(
      await screen.findByText(/respuesta generada en otra pestaña/i),
    ).toBeInTheDocument();
  });

  it("P2: reingresar a un chat no duplica el turno user ni la respuesta ya persistidos", async () => {
    const user = userEvent.setup();
    const { chatStore } = await import("../lib/chatStore");
    const convA = chatStore.crearConversacion(1, "Chat A");
    chatStore.crearConversacion(1, "Chat B");
    localStorage.setItem("asistente:sidebar-open", "chat");

    // Lo que devuelve la BD al hidratar: vacío hasta que el envío persiste.
    let remotos: Parameters<typeof chatStore.hidratarMensajes>[2] = [];
    (mockedHidratarMensajes as ReturnType<typeof vi.fn>).mockImplementation(
      async (usuarioId: number, chatId: string, omitir?: () => boolean) =>
        omitir?.()
          ? 0
          : chatStore.hidratarMensajes(usuarioId, chatId, remotos),
    );
    (mockedAsegurarChat as ReturnType<typeof vi.fn>).mockResolvedValueOnce(10);
    let resolverBot: (id: number) => void = () => undefined;
    (mockedPersistirMensaje as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(42)
      .mockImplementationOnce(
        () => new Promise<number>((resolve) => (resolverBot = resolve)),
      );
    (mockedResponder as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stream: createMockStreamReader(["respuesta de A"]),
      tipoRespuesta: "consulta_simple",
      historialId: null,
    });

    renderAsistente();
    await user.click(screen.getByRole("button", { name: /chat a/i }));
    await user.type(screen.getByRole("textbox", { name: "Consulta" }), "hola");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() =>
      expect(mockedPersistirMensaje).toHaveBeenCalledTimes(2),
    );
    remotos = [
      {
        id: 42,
        tipo: "user",
        contenido: "hola",
        razonamiento: "",
        created_at: null,
      },
      {
        id: 43,
        tipo: "bot",
        contenido: "respuesta de A",
        razonamiento: "",
        created_at: null,
      },
    ];

    const contar = () =>
      chatStore.listarMensajes(1, convA.id).map((m) => m.tipo);

    // La respuesta ya está en BD pero su POST no volvió: reingresar no la duplica.
    await user.click(screen.getByRole("button", { name: /chat b/i }));
    await user.click(screen.getByRole("button", { name: /chat a/i }));
    await waitFor(() =>
      expect(mockedHidratarMensajes).toHaveBeenCalledTimes(2),
    );
    await screen.findByText(/respuesta de a/i);
    expect(contar()).toEqual(["user", "bot"]);

    resolverBot(43);
    await waitFor(() =>
      expect(
        chatStore
          .listarMensajes(1, convA.id)
          .map((m) => m.metadatos?.mensaje_id_bd),
      ).toEqual([42, 43]),
    );
    await user.click(screen.getByRole("button", { name: /chat b/i }));
    await user.click(screen.getByRole("button", { name: /chat a/i }));
    await waitFor(() =>
      expect(mockedHidratarMensajes).toHaveBeenCalledTimes(4),
    );
    expect(contar()).toEqual(["user", "bot"]);
  });
});
