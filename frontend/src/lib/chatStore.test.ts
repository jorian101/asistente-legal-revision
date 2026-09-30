// Test minimo del store local de conversaciones. Verifica crear / renombrar /
// archivar / fijar / mover a carpeta y agregar mensaje. El store vive en
// localStorage, asi que simulamos storage en setup y limpiamos entre tests.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatStore } from "./chatStore";

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
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

describe("chatStore", () => {
  const USUARIO = 7;

  it("crea una conversacion con titulo por defecto", () => {
    const conv = chatStore.crearConversacion(USUARIO, "");
    expect(conv.titulo).toBe("Sin titulo");
    expect(conv.estado).toBe("activo");
    expect(conv.propietario_id).toBe(USUARIO);
  });

  it("renombra, archiva y desfijar no tocan eliminado", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Inicial");
    chatStore.renombrarConversacion(USUARIO, conv.id, "Renombrado");
    chatStore.archivarConversacion(USUARIO, conv.id);
    expect(
      chatStore.listarConversaciones(USUARIO).find((c) => c.id === conv.id)
        ?.estado,
    ).toBe("archivado");
    chatStore.desarchivarConversacion(USUARIO, conv.id);
    expect(
      chatStore.listarConversaciones(USUARIO).find((c) => c.id === conv.id)
        ?.estado,
    ).toBe("activo");
  });

  it("asociarExpediente vincula un expediente a la conversacion", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Caso 1");
    expect(conv.expediente_id).toBeNull();
    chatStore.asociarExpediente(USUARIO, conv.id, 42);
    const actualizada = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(actualizada?.expediente_id).toBe(42);
  });

  it("fijar crea el espacio Fijados y mover a carpeta personalizada funciona", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Caso");
    chatStore.fijarConversacion(USUARIO, conv.id);
    const convFijada = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(convFijada?.espacio_trabajo_id).not.toBeNull();

    const espacio = chatStore.crearEspacio(USUARIO, "Recursos");
    chatStore.moverACarpeta(USUARIO, conv.id, espacio.id);
    const movida = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(movida?.espacio_trabajo_id).toBe(espacio.id);

    chatStore.eliminarEspacio(USUARIO, espacio.id);
    const trasEliminar = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(trasEliminar?.espacio_trabajo_id).toBeNull();
  });

  it("agregar mensaje incrementa posicion y actualiza ultimo_mensaje_at", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Chat");
    const m1 = chatStore.agregarMensaje(USUARIO, conv.id, "user", "Pregunta 1");
    const m2 = chatStore.agregarMensaje(USUARIO, conv.id, "bot", "Respuesta 1");
    expect(m1.posicion).toBe(1);
    expect(m2.posicion).toBe(2);
    const convActualizada = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(convActualizada?.ultimo_mensaje_at).not.toBeNull();
  });

  it("actualizarMensaje persiste el contenido del mensaje (streaming)", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Chat");
    const m = chatStore.agregarMensaje(USUARIO, conv.id, "bot", "");
    const actualizado = chatStore.actualizarMensaje(
      USUARIO,
      m.id,
      "Respuesta acumulada por streaming",
    );
    expect(actualizado?.contenido).toBe("Respuesta acumulada por streaming");
    const mensajes = chatStore.listarMensajes(USUARIO, conv.id);
    expect(mensajes.find((x) => x.id === m.id)?.contenido).toBe(
      "Respuesta acumulada por streaming",
    );
    expect(chatStore.actualizarMensaje(USUARIO, "no-existe", "x")).toBeNull();
  });

  it("buscarConversaciones hace match por titulo y por contenido", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Prueba");
    chatStore.agregarMensaje(USUARIO, conv.id, "user", "buscar token-xyz");
    expect(
      chatStore.buscarConversaciones(USUARIO, "Prueba").map((c) => c.id),
    ).toContain(conv.id);
    expect(
      chatStore.buscarConversaciones(USUARIO, "token-xyz").map((c) => c.id),
    ).toContain(conv.id);
    expect(chatStore.buscarConversaciones(USUARIO, "no-existe")).toHaveLength(
      0,
    );
  });
});

describe("corpus_refs (chips T2)", () => {
  const USUARIO = 7;
  it("asociarCorpusRef agrega sin duplicar y quitarCorpusRef remueve", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Chips");
    expect(conv.corpus_refs ?? []).toEqual([]);
    chatStore.asociarCorpusRef(USUARIO, conv.id, "SCP-0623-2024-S4");
    chatStore.asociarCorpusRef(USUARIO, conv.id, "SCP-0623-2024-S4");
    chatStore.asociarCorpusRef(USUARIO, conv.id, "LIB-ATIENZA-INTERP-2019");
    const listadas = chatStore.listarConversaciones(USUARIO);
    expect(listadas.find((c) => c.id === conv.id)?.corpus_refs).toEqual([
      "SCP-0623-2024-S4",
      "LIB-ATIENZA-INTERP-2019",
    ]);
    chatStore.quitarCorpusRef(USUARIO, conv.id, "SCP-0623-2024-S4");
    expect(
      chatStore.listarConversaciones(USUARIO).find((c) => c.id === conv.id)
        ?.corpus_refs,
    ).toEqual(["LIB-ATIENZA-INTERP-2019"]);
  });
});

describe("chatStore sin espacio en localStorage", () => {
  it("no lanza si setItem falla por cuota llena", () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("quota", "QuotaExceededError");
      });
    expect(() => chatStore.crearConversacion(99, "Consulta")).not.toThrow();
    spy.mockRestore();
  });
});
