// InputArea: botones para fijar fuentes (normas, jurisprudencia, doctrina) y adjuntar expediente.

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InputArea } from "../components/chat/InputArea";

function montar() {
  const handlers = {
    onAdjuntarExpediente: vi.fn(),
    onAdjuntarNormas: vi.fn(),
    onAdjuntarDoctrina: vi.fn(),
    onAdjuntarJurisprudencia: vi.fn(),
  };
  render(
    <InputArea
      value=""
      onChange={() => {}}
      onSend={() => {}}
      onCancel={() => {}}
      cargando={false}
      {...handlers}
    />,
  );
  return handlers;
}

describe("InputArea — fuentes", () => {
  it("ofrece normas, jurisprudencia y doctrina, cada una con su acción", async () => {
    const h = montar();

    await userEvent.click(
      screen.getByRole("button", { name: "Fijar normas en la consulta" }),
    );
    await userEvent.click(
      screen.getByRole("button", {
        name: "Agregar jurisprudencia a la consulta",
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Agregar doctrina a la consulta" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Adjuntar expediente a la consulta" }),
    );

    expect(h.onAdjuntarNormas).toHaveBeenCalledTimes(1);
    expect(h.onAdjuntarJurisprudencia).toHaveBeenCalledTimes(1);
    expect(h.onAdjuntarDoctrina).toHaveBeenCalledTimes(1);
    expect(h.onAdjuntarExpediente).toHaveBeenCalledTimes(1);
  });
});

describe("InputArea — Enter", () => {
  afterEach(() => vi.unstubAllGlobals());

  function conTexto(onSend = vi.fn()) {
    render(
      <InputArea
        value="¿Qué dice el art. 5?"
        onChange={() => {}}
        onSend={onSend}
        onCancel={() => {}}
        onAdjuntarExpediente={() => {}}
        onAdjuntarNormas={() => {}}
        onAdjuntarDoctrina={() => {}}
        onAdjuntarJurisprudencia={() => {}}
        cargando={false}
      />,
    );
    return onSend;
  }

  it("con teclado físico Enter envía", async () => {
    const onSend = conTexto();
    await userEvent.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "{Enter}",
    );
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("en táctil Enter no envía (es salto de línea)", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q === "(pointer: coarse)",
    }));
    const onSend = conTexto();
    await userEvent.type(
      screen.getByRole("textbox", { name: "Consulta" }),
      "{Enter}",
    );
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Enter que confirma una composición (IME/acento) no envía", () => {
    const onSend = conTexto();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Consulta" }), {
      key: "Enter",
      isComposing: true,
    });
    expect(onSend).not.toHaveBeenCalled();
  });
});
