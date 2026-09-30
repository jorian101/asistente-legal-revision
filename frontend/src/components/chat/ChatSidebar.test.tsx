// Test minimo del sidebar del chat. Cubre el render y la propagacion de
// acciones basicas (seleccionar, archivar, fijar, mover a carpeta, eliminar).
// Se monta contra chatStore real (localStorage mock) — el store ya tiene
// cobertura propia; acı valido que la UI llama las acciones correctas.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";

import { ChatSidebar } from "./ChatSidebar";
import { chatStore } from "../../lib/chatStore";
import type { Conversacion, EspacioTrabajo } from "../../lib/chatTypes";

interface MemoriaLocalStorage {
  [k: string]: string;
}

let memoria: MemoriaLocalStorage;

beforeEach(() => {
  memoria = {};
  globalThis.localStorage = {
    getItem: (k) => memoria[k] ?? null,
    setItem: (k, v) => {
      memoria[k] = v;
    },
    removeItem: (k) => {
      delete memoria[k];
    },
    clear: () => {
      memoria = {};
    },
    key: (i) => Object.keys(memoria)[i] ?? null,
    length: 0,
  } as Storage;
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

const USUARIO = 11;

function setupConversaciones(): {
  conversaciones: Conversacion[];
  espacios: EspacioTrabajo[];
} {
  const conv1 = chatStore.crearConversacion(USUARIO, "Caso A");
  const conv2 = chatStore.crearConversacion(USUARIO, "Caso B");
  const carpeta = chatStore.crearEspacio(USUARIO, "Recursos");
  return {
    conversaciones: [conv1, conv2],
    espacios: [carpeta],
  };
}

function setupHandlers() {
  return {
    onSeleccionarConversacion: vi.fn(),
    onRenombrarConversacion: vi.fn(),
    onEliminarConversacion: vi.fn(),
    onArchivarConversacion: vi.fn(),
    onDesarchivarConversacion: vi.fn(),
    onFijarConversacion: vi.fn(),
    onDesfijarConversacion: vi.fn(),
    onMoverACarpeta: vi.fn(),
    onNuevaConversacion: vi.fn(),
    onCerrar: vi.fn(),
    onBuscar: vi.fn(),
    onCrearCarpeta: vi.fn(),
    onRenombrarEspacio: vi.fn(),
    onEliminarEspacio: vi.fn(),
  };
}

describe("ChatSidebar", () => {
  it("rendera los botones principales de accion", () => {
    const handlers = setupHandlers();
    render(
      <ChatSidebar
        conversaciones={[]}
        espacios={[]}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    expect(
      screen.getByRole("button", { name: /nueva conversacion/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /buscar/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /archivados/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /nueva carpeta/i }),
    ).toBeInTheDocument();
  });

  it("abre el modal de busqueda al pulsar Buscar", () => {
    const handlers = setupHandlers();
    const { conversaciones, espacios } = setupConversaciones();
    render(
      <ChatSidebar
        conversaciones={conversaciones}
        espacios={espacios}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /buscar/i }));
    expect(
      screen.getByRole("dialog", { name: /buscar conversaciones/i }),
    ).toBeInTheDocument();
  });

  it("los resultados de busqueda ofrecen eliminar (soft) y renombrar", () => {
    const handlers = setupHandlers();
    const { conversaciones } = setupConversaciones();
    (handlers.onBuscar as ReturnType<typeof vi.fn>).mockReturnValue(
      conversaciones,
    );
    render(
      <ChatSidebar
        conversaciones={conversaciones}
        espacios={[]}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /buscar/i }));
    fireEvent.change(screen.getByRole("textbox", { name: "Buscar" }), {
      target: { value: "caso" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Eliminar Caso A" }));
    expect(handlers.onEliminarConversacion).toHaveBeenCalledWith(
      conversaciones[0].id,
    );

    fireEvent.click(screen.getByRole("button", { name: "Renombrar Caso B" }));
    const input = screen.getByRole("textbox", {
      name: "Nombre de la conversacion",
    });
    fireEvent.change(input, { target: { value: "Caso B renombrado" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(handlers.onRenombrarConversacion).toHaveBeenCalledWith(
      conversaciones[1].id,
      "Caso B renombrado",
    );
  });

  it("abre el modal de archivados y muestra el contador", () => {
    const handlers = setupHandlers();
    chatStore.crearConversacion(USUARIO, "Caso A");
    chatStore.crearConversacion(USUARIO, "Caso B");
    const conversaciones = chatStore.listarConversaciones(USUARIO);
    const convArchivar = conversaciones[0];
    chatStore.archivarConversacion(USUARIO, convArchivar.id);
    const conversacionesActualizadas = chatStore.listarConversaciones(USUARIO);
    render(
      <ChatSidebar
        conversaciones={conversacionesActualizadas}
        espacios={[]}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    expect(
      screen.getByRole("button", { name: /archivados \(1\)/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /archivados \(1\)/i }));
    expect(
      screen.getByRole("dialog", { name: /chats archivados/i }),
    ).toBeInTheDocument();
  });

  it("click en una conversacion llama onSeleccionarConversacion", () => {
    const handlers = setupHandlers();
    const { conversaciones } = setupConversaciones();
    render(
      <ChatSidebar
        conversaciones={conversaciones}
        espacios={[]}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    const btn = screen.getByRole("button", { name: /caso a/i });
    fireEvent.click(btn);
    expect(handlers.onSeleccionarConversacion).toHaveBeenCalledWith(
      conversaciones[0].id,
    );
  });

  it("muestra conversaciones sueltas y carpetas con su conteo", () => {
    const handlers = setupHandlers();
    const { conversaciones, espacios } = setupConversaciones();
    chatStore.moverACarpeta(USUARIO, conversaciones[0].id, espacios[0].id);
    const convActualizadas = chatStore.listarConversaciones(USUARIO);
    render(
      <ChatSidebar
        conversaciones={convActualizadas}
        espacios={espacios}
        conversacionActivaId={null}
        {...handlers}
      />,
    );
    // Caso B sigue suelta
    expect(screen.getByText(/caso b/i)).toBeInTheDocument();
    // Caso A esta dentro de la carpeta Recursos (header visible)
    expect(screen.getByText(/recursos/i)).toBeInTheDocument();
    const carpeta = screen.getByText(/recursos/i).closest("button");
    expect(carpeta).not.toBeNull();
    // El conteo de la carpeta debe ser 1
    expect(within(carpeta!).getByText("1")).toBeInTheDocument();
  });

  it("crea la carpeta como 'Sin título' sin prompt y entra en edicion inline", () => {
    const handlers = setupHandlers();
    const promptSpy = vi.spyOn(window, "prompt");
    const crearSpy = vi.spyOn(chatStore, "crearEspacio");

    function Harness() {
      const [conversaciones, setConversaciones] = useState<Conversacion[]>([]);
      const [espacios, setEspacios] = useState<EspacioTrabajo[]>([]);
      const recargar = () => {
        setConversaciones(chatStore.listarConversaciones(USUARIO));
        setEspacios(chatStore.listarEspacios(USUARIO));
      };
      const handleCrear = (nombre: string) => {
        const esp = chatStore.crearEspacio(USUARIO, nombre);
        recargar();
        return esp.id;
      };
      return (
        <ChatSidebar
          conversaciones={conversaciones}
          espacios={espacios}
          conversacionActivaId={null}
          {...handlers}
          onCrearCarpeta={handleCrear}
          onRenombrarEspacio={(id, nombre) => {
            chatStore.renombrarEspacio(USUARIO, id, nombre);
            recargar();
            handlers.onRenombrarEspacio(id, nombre);
          }}
        />
      );
    }

    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /nueva carpeta/i }));

    // Sin window.prompt: la carpeta se crea al instante con "Sin título".
    expect(promptSpy).not.toHaveBeenCalled();
    expect(crearSpy).toHaveBeenCalledWith(USUARIO, "Sin título");

    // La carpeta aparece en modo edicion (input con el nombre seleccionado).
    const input = screen.getByDisplayValue("Sin título");
    expect(input).toBeInTheDocument();

    // Renombrar en el mismo input con Enter cierra la edicion.
    fireEvent.change(input, { target: { value: "Caso Penal" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(handlers.onRenombrarEspacio).toHaveBeenCalledWith(
      expect.any(String),
      "Caso Penal",
    );
    expect(screen.queryByDisplayValue("Caso Penal")).not.toBeInTheDocument();
    expect(screen.getByText(/caso penal/i)).toBeInTheDocument();
  });
});
