// Tests chatStore: store local de conversaciones (localStorage).
//
// Cubre hidratarMensajes (P2/F5): fusiona mensajes remotos (BD) que no
// existen localmente, dedupe por mensaje_id_bd, sin pisar contenido local,
// preservando el orden cronológico real.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatStore } from "../lib/chatStore";

const USUARIO_ID = 1;

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("chatStore.hidratarMensajes", () => {
  it("agrega mensajes remotos que no existen localmente", () => {
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat P2");
    chatStore.agregarMensaje(USUARIO_ID, conv.id, "user", "hola local");

    const agregados = chatStore.hidratarMensajes(USUARIO_ID, conv.id, [
      {
        id: 501,
        tipo: "bot",
        contenido: "respuesta generada en otra pestaña",
        razonamiento: "",
        // Posterior a "hola local" (creado con AHORA() = tiempo real del
        // test): el orden cronológico debe dejarlo despues.
        created_at: "2099-01-01T00:00:00.000Z",
      },
    ]);

    expect(agregados).toBe(1);
    const mensajes = chatStore.listarMensajes(USUARIO_ID, conv.id);
    expect(mensajes).toHaveLength(2);
    expect(mensajes[1].contenido).toBe("respuesta generada en otra pestaña");
    expect(mensajes[1].metadatos?.mensaje_id_bd).toBe(501);
  });

  it("dedupea por mensaje_id_bd — no duplica un mensaje ya hidratado o propio", () => {
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat P2");
    const bot = chatStore.agregarMensaje(
      USUARIO_ID,
      conv.id,
      "bot",
      "ya la tengo",
    );
    chatStore.asociarMensajeBd(USUARIO_ID, bot.id, 501);

    const agregados = chatStore.hidratarMensajes(USUARIO_ID, conv.id, [
      {
        id: 501,
        tipo: "bot",
        contenido: "version del servidor (no debe pisar la local)",
        razonamiento: "",
        created_at: "2026-09-23T10:00:00.000Z",
      },
    ]);

    expect(agregados).toBe(0);
    const mensajes = chatStore.listarMensajes(USUARIO_ID, conv.id);
    expect(mensajes).toHaveLength(1);
    // No se pisó el contenido local con el del servidor.
    expect(mensajes[0].contenido).toBe("ya la tengo");
  });

  it("intercala mensajes remotos en el orden cronológico real (created_at)", () => {
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat P2");
    // Local: dos turnos ya escritos en esta pestaña (posicion 1, 2).
    chatStore.agregarMensaje(USUARIO_ID, conv.id, "user", "pregunta 1");
    const bot1 = chatStore.agregarMensaje(
      USUARIO_ID,
      conv.id,
      "bot",
      "respuesta 1",
    );
    chatStore.asociarMensajeBd(USUARIO_ID, bot1.id, 601);

    // Remoto: un turno posterior (otra pestaña) con posicion propia 1 en su
    // numeración de origen, pero created_at más nuevo que los locales.
    const agregados = chatStore.hidratarMensajes(USUARIO_ID, conv.id, [
      {
        id: 602,
        tipo: "user",
        contenido: "pregunta 2 (otra pestaña)",
        razonamiento: "",
        created_at: "2099-01-01T00:00:00.000Z",
      },
    ]);

    expect(agregados).toBe(1);
    const mensajes = chatStore.listarMensajes(USUARIO_ID, conv.id);
    expect(mensajes.map((m) => m.contenido)).toEqual([
      "pregunta 1",
      "respuesta 1",
      "pregunta 2 (otra pestaña)",
    ]);
    // Renumerado 1..N por orden cronológico, sin colisiones de posicion.
    expect(mensajes.map((m) => m.posicion)).toEqual([1, 2, 3]);
  });

  it("asocia el id remoto a un mensaje local legado sin mensaje_id_bd en vez de duplicarlo", () => {
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat legado");
    chatStore.agregarMensaje(USUARIO_ID, conv.id, "user", "hola");
    chatStore.agregarMensaje(USUARIO_ID, conv.id, "user", "hola");

    const agregados = chatStore.hidratarMensajes(USUARIO_ID, conv.id, [
      {
        id: 42,
        tipo: "user",
        contenido: "hola",
        razonamiento: "",
        created_at: "2026-09-23T10:00:00.000Z",
      },
    ]);

    expect(agregados).toBe(0);
    const mensajes = chatStore.listarMensajes(USUARIO_ID, conv.id);
    expect(mensajes).toHaveLength(2);
    expect(mensajes.map((m) => m.metadatos?.mensaje_id_bd ?? null)).toEqual([
      42,
      null,
    ]);
  });

  it("no hace nada si no hay mensajes remotos nuevos", () => {
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat P2");
    const agregados = chatStore.hidratarMensajes(USUARIO_ID, conv.id, []);
    expect(agregados).toBe(0);
    expect(chatStore.listarMensajes(USUARIO_ID, conv.id)).toHaveLength(0);
  });

  it("ordena por fecha real aunque el servidor use otro formato u offset", () => {
    vi.useFakeTimers();
    const conv = chatStore.crearConversacion(USUARIO_ID, "Chat P2");
    vi.setSystemTime(new Date("2026-09-23T10:00:00.000Z"));
    chatStore.agregarMensaje(USUARIO_ID, conv.id, "user", "pregunta local");

    chatStore.hidratarMensajes(USUARIO_ID, conv.id, [
      {
        id: 701,
        tipo: "bot",
        contenido: "respuesta remota",
        razonamiento: "",
        // 10:00:01Z: como texto ("06:...") queda antes que la pregunta local.
        created_at: "2026-09-23T06:00:01.123456-04:00",
      },
    ]);

    expect(
      chatStore.listarMensajes(USUARIO_ID, conv.id).map((m) => m.contenido),
    ).toEqual(["pregunta local", "respuesta remota"]);
  });
});
