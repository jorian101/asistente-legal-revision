// MessagesScroll: boton flotante para bajar rapido cuando el usuario se
// aleja del fondo. jsdom no mide layout, asi que mockeamos las metricas de
// scroll del contenedor y disparamos el evento.

import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { MessagesScroll } from "./MessagesScroll";
import type { Mensaje } from "../../lib/chatTypes";

function mensaje(
  id: string,
  tipo: "user" | "bot",
  contenido = `contenido ${id}`,
): Mensaje {
  return {
    id,
    chat_id: "c1",
    tipo,
    razonamiento: "",
    contenido,
    estado: "activo",
    posicion: 1,
    metadatos: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function definirScroll(
  el: HTMLElement,
  {
    scrollHeight,
    clientHeight,
    scrollTop,
  }: { scrollHeight: number; clientHeight: number; scrollTop: number },
) {
  Object.defineProperty(el, "scrollHeight", {
    value: scrollHeight,
    configurable: true,
  });
  Object.defineProperty(el, "clientHeight", {
    value: clientHeight,
    configurable: true,
  });
  // Escribible: el componente escribe scrollTop y queremos poder asertarlo.
  Object.defineProperty(el, "scrollTop", {
    value: scrollTop,
    writable: true,
    configurable: true,
  });
}

describe("MessagesScroll (scroll-down)", () => {
  it("muestra el boton cuando el usuario se aleja del fondo", () => {
    render(
      <MessagesScroll
        mensajes={[mensaje("m1", "user"), mensaje("m2", "bot")]}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Desplazarse hacia abajo" }),
    ).not.toBeInTheDocument();

    const scrollEl = screen.getByTestId("messages-scroll");
    definirScroll(scrollEl, {
      scrollHeight: 500,
      clientHeight: 100,
      scrollTop: 0,
    });
    fireEvent.scroll(scrollEl);

    expect(
      screen.getByRole("button", { name: "Desplazarse hacia abajo" }),
    ).toBeInTheDocument();
  });

  it("al estar al fondo el boton desaparece", () => {
    render(<MessagesScroll mensajes={[mensaje("m1", "user")]} />);
    const scrollEl = screen.getByTestId("messages-scroll");
    definirScroll(scrollEl, {
      scrollHeight: 500,
      clientHeight: 100,
      scrollTop: 0,
    });
    fireEvent.scroll(scrollEl);
    expect(
      screen.getByRole("button", { name: "Desplazarse hacia abajo" }),
    ).toBeInTheDocument();

    // Vuelve al fondo (scrollTop cerca de scrollHeight - clientHeight).
    definirScroll(scrollEl, {
      scrollHeight: 500,
      clientHeight: 100,
      scrollTop: 400,
    });
    fireEvent.scroll(scrollEl);
    expect(
      screen.queryByRole("button", { name: "Desplazarse hacia abajo" }),
    ).not.toBeInTheDocument();
  });

  it("al cambiar de conversación vuelve al fondo (no hereda el scroll)", () => {
    const { rerender } = render(
      <MessagesScroll
        mensajes={[mensaje("m1", "user")]}
        conversacion={{ id: "a", expediente_id: null }}
      />,
    );
    const scrollEl = screen.getByTestId("messages-scroll");
    definirScroll(scrollEl, {
      scrollHeight: 500,
      clientHeight: 100,
      scrollTop: 0,
    });
    fireEvent.scroll(scrollEl);
    expect(
      screen.getByRole("button", { name: "Desplazarse hacia abajo" }),
    ).toBeInTheDocument();

    // El auto-scroll escribe scrollTop al cambiar de conversación.
    rerender(
      <MessagesScroll
        mensajes={[mensaje("m9", "user")]}
        conversacion={{ id: "b", expediente_id: null }}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Desplazarse hacia abajo" }),
    ).not.toBeInTheDocument();
  });

  it("el usuario puede subir aunque el asistente siga escribiendo", () => {
    const { rerender } = render(
      <MessagesScroll
        mensajes={[mensaje("m1", "user"), mensaje("m2", "bot")]}
      />,
    );
    const scrollEl = screen.getByTestId("messages-scroll");
    definirScroll(scrollEl, {
      scrollHeight: 1000,
      clientHeight: 100,
      scrollTop: 900,
    });

    // El gesto suelta el pin antes de que el navegador mueva la posición y
    // antes de que el typewriter mute el DOM (que es el mismo frame).
    fireEvent.wheel(scrollEl, { deltaY: -120 });
    definirScroll(scrollEl, {
      scrollHeight: 1000,
      clientHeight: 100,
      scrollTop: 200,
    });
    rerender(
      <MessagesScroll
        mensajes={[
          mensaje("m1", "user"),
          mensaje("m2", "bot", `contenido m2 ${"x".repeat(400)}`),
        ]}
      />,
    );

    // No nos devuelve al fondo y el botón para bajar queda disponible.
    expect(scrollEl.scrollTop).toBe(200);
    expect(
      screen.getByRole("button", { name: "Desplazarse hacia abajo" }),
    ).toBeInTheDocument();
  });

  it("sigue al fondo cuando el contenido crece si el usuario no scrollea", () => {
    const { rerender } = render(
      <MessagesScroll
        mensajes={[mensaje("m1", "user"), mensaje("m2", "bot")]}
      />,
    );
    const scrollEl = screen.getByTestId("messages-scroll");
    definirScroll(scrollEl, {
      scrollHeight: 1000,
      clientHeight: 100,
      scrollTop: 900,
    });
    fireEvent.scroll(scrollEl);

    // El typewriter hace crecer el contenido: seguimos pegados al fondo.
    definirScroll(scrollEl, {
      scrollHeight: 1400,
      clientHeight: 100,
      scrollTop: 900,
    });
    rerender(
      <MessagesScroll
        mensajes={[
          mensaje("m1", "user"),
          mensaje("m2", "bot", `contenido m2 ${"x".repeat(400)}`),
        ]}
      />,
    );

    expect(scrollEl.scrollTop).toBe(1400);
    expect(
      screen.queryByRole("button", { name: "Desplazarse hacia abajo" }),
    ).not.toBeInTheDocument();
  });
});
