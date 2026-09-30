// ChatMessage: markdown en el mensaje del asistente.
//
// El bot renderiza su contenido como markdown (marked) sanitizado (DOMPurify);
// el user se muestra en texto plano. Incluye test anti-XSS para contenido
// hostil que pueda emitir el LLM.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ChatMessage } from "./ChatMessage";
import { getFeedback } from "../../lib/feedback";
import type { Mensaje } from "../../lib/chatTypes";

function mensaje(contenido: string, tipo: "bot" | "user"): Mensaje {
  return {
    id: tipo === "bot" ? "m-bot" : "m-user",
    chat_id: "c1",
    tipo,
    razonamiento: "",
    contenido,
    estado: "activo",
    posicion: 1,
    metadatos: null,
    created_at: "2026-01-01T00:00:00Z",
    fragmentos: [],
    scores: [],
    latencia_ms: null,
    tipo_respuesta: null,
  };
}

describe("ChatMessage (markdown del asistente)", () => {
  it("rendera markdown del mensaje bot como HTML", () => {
    render(<ChatMessage mensaje={mensaje("**negrita** y `codigo`", "bot")} />);
    expect(screen.getByText("negrita").tagName).toBe("STRONG");
    expect(screen.getByText("codigo").tagName).toBe("CODE");
  });

  it("rendera bloques de codigo en pre>code", () => {
    const { container } = render(
      <ChatMessage mensaje={mensaje("```js\nconst x = 1;\n```", "bot")} />,
    );
    const code = container.querySelector("pre code");
    expect(code).not.toBeNull();
    expect(code?.textContent).toContain("const x = 1");
  });

  it("sanitiza HTML/JS peligroso del LLM (anti-XSS)", () => {
    const { container } = render(
      <ChatMessage
        mensaje={mensaje(
          '<script>alert(1)</script><img src="x" onerror="alert(2)">\n\n**ok**',
          "bot",
        )}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(screen.getByText("ok").tagName).toBe("STRONG");
  });

  it("el mensaje user se muestra en texto plano (sin markdown)", () => {
    const { container } = render(
      <ChatMessage mensaje={mensaje("**literal**", "user")} />,
    );
    expect(container.textContent).toContain("**literal**");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("like/dislike actualiza el estado del boton y persiste en localStorage", () => {
    localStorage.clear();
    const { getByRole } = render(
      <ChatMessage mensaje={mensaje("resp", "bot")} />,
    );

    const like = getByRole("button", { name: "Like" });
    fireEvent.click(like);
    expect(getByRole("button", { name: "Quitar like" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(getFeedback("m-bot")).toBe("like");

    // Click de nuevo desactiva (toggle)
    fireEvent.click(getByRole("button", { name: "Quitar like" }));
    expect(getByRole("button", { name: "Like" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(getFeedback("m-bot")).toBeNull();

    // Dislike marca su estado
    fireEvent.click(getByRole("button", { name: "Dislike" }));
    expect(getFeedback("m-bot")).toBe("dislike");
  });

  it("copia el contenido de la respuesta al portapapeles", async () => {
    localStorage.clear();
    const writeText = vi.fn().mockResolvedValue(undefined) as unknown as (
      text: string,
    ) => Promise<void>;
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    const { getByRole } = render(
      <ChatMessage mensaje={mensaje("**texto a copiar**", "bot")} />,
    );
    fireEvent.click(getByRole("button", { name: "Copiar respuesta" }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("**texto a copiar**");
    });
    expect(
      getByRole("button", { name: "Respuesta copiada" }),
    ).toBeInTheDocument();
  });
});

describe("ChatMessage (boton guardar borrador)", () => {
  function mensajeBorrador(tipo: string): Mensaje {
    return {
      ...mensaje("Texto del auto de vista", "bot"),
      tipo_respuesta: tipo,
    };
  }

  it("muestra Guardar en Mis Borradores cuando el tipo genera borrador", () => {
    render(
      <ChatMessage
        mensaje={mensajeBorrador("auto_vista_consulta")}
        conversacion={{ id: "c1", expediente_id: 5, chat_id_bd: null }}
        puedeGenerarBorrador={true}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Guardar en Mis Borradores" }),
    ).toBeInTheDocument();
  });

  it("no muestra el boton para consulta_simple", () => {
    render(<ChatMessage mensaje={mensajeBorrador("consulta_simple")} />);
    expect(
      screen.queryByRole("button", { name: "Guardar en Mis Borradores" }),
    ).not.toBeInTheDocument();
  });

  it("deshabilita el boton sin expediente o sin obras", () => {
    render(
      <ChatMessage
        mensaje={mensajeBorrador("auto_vista_consulta")}
        conversacion={{ id: "c1", expediente_id: null, chat_id_bd: null }}
        puedeGenerarBorrador={false}
      />,
    );
    const btn = screen.getByRole("button", {
      name: "Adjunta un expediente para guardar el borrador",
    });
    expect(btn).toBeDisabled();
  });

  it("muestra Actualizar mi borrador cuando ya esta guardado", () => {
    render(
      <ChatMessage
        mensaje={{ ...mensajeBorrador("auto_vista_consulta"), borrador_id: 7 }}
        conversacion={{ id: "c1", expediente_id: 5, chat_id_bd: 3 }}
        puedeGenerarBorrador={true}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Actualizar mi borrador" }),
    ).toBeInTheDocument();
  });

  it("dispara onGuardarBorrador al pulsar el boton", () => {
    const onGuardar = vi.fn();
    const m = mensajeBorrador("auto_vista_consulta");
    render(
      <ChatMessage
        mensaje={m}
        conversacion={{ id: "c1", expediente_id: 5, chat_id_bd: null }}
        puedeGenerarBorrador={true}
        onGuardarBorrador={onGuardar}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Guardar en Mis Borradores" }),
    );
    expect(onGuardar).toHaveBeenCalledWith(m);
  });
});

describe("ChatMessage (quitar del historial)", () => {
  function mensajeConHistorial(historialId?: number): Mensaje {
    return { ...mensaje("resp", "bot"), historial_id: historialId };
  }

  it("no muestra la accion sin callback", () => {
    render(<ChatMessage mensaje={mensajeConHistorial(9)} />);
    expect(
      screen.queryByRole("button", { name: "Quitar del historial" }),
    ).toBeNull();
  });

  it("no la muestra si el mensaje no tiene historial_id", () => {
    render(
      <ChatMessage
        mensaje={mensajeConHistorial(undefined)}
        onEliminarHistorial={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Quitar del historial" }),
    ).toBeNull();
  });

  it("no la muestra en el mensaje del usuario", () => {
    render(
      <ChatMessage
        mensaje={{ ...mensaje("pregunta", "user"), historial_id: 9 }}
        onEliminarHistorial={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Quitar del historial" }),
    ).toBeNull();
  });

  it("la muestra y dispara el callback con el mensaje", () => {
    const onEliminar = vi.fn();
    const m = mensajeConHistorial(9);
    render(<ChatMessage mensaje={m} onEliminarHistorial={onEliminar} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Quitar del historial" }),
    );
    expect(onEliminar).toHaveBeenCalledWith(m);
  });
});

describe("ChatMessage (sin porcentaje de relevancia)", () => {
  it("no muestra porcentaje ni medidor: sin reranker el score RRF no mide relevancia", () => {
    const msg = {
      ...mensaje("Texto con cita", "bot"),
      fragmentos: [
        {
          id: 1,
          norma_id: 1,
          obra_id: null,
          texto: "Fragmento de prueba",
          referencia: "Articulo 1",
          nivel_jerarquico: 1,
        },
      ],
      scores: [0.5],
    };
    render(<ChatMessage mensaje={msg} />);

    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.queryByText(/\d+%/)).toBeNull();
  });
});

describe("ChatMessage (fuentes enriquecidas)", () => {
  it("muestra tipo de documento y expediente en un obrado", () => {
    const msg = {
      ...mensaje("VISTOS: ...", "bot"),
      fragmentos: [
        {
          id: 10,
          norma_id: null,
          obra_id: 5,
          texto: "VISTOS: ...",
          referencia: null,
          nivel_jerarquico: null,
          obra_tipo: "auto_vista",
          obra_fecha_documento: "12/05/2025",
          expediente_numero: "3349",
        },
      ],
      scores: [0.72],
    };
    render(<ChatMessage mensaje={msg} />);

    expect(screen.getByText("OBRADO")).toBeTruthy();
    // Ya no queda solo en "OBRADO": dice qué pieza y dónde buscarla.
    expect(screen.getByText(/Auto Vista/)).toBeTruthy();
    expect(screen.getByText(/Exp\. 3349/)).toBeTruthy();
    expect(screen.getByText(/12\/05\/2025/)).toBeTruthy();
  });

  it("muestra el nombre formal de la norma junto a su articulo", () => {
    const msg = {
      ...mensaje("resp", "bot"),
      fragmentos: [
        {
          id: 5,
          norma_id: 1,
          obra_id: null,
          texto: "Art. 3 ...",
          referencia: "LOJM 3",
          nivel_jerarquico: 4,
          norma_nombre: "Ley Organica de la Justicia Militar",
          norma_abreviatura: "LOJM",
        },
      ],
      scores: [0.9],
    };
    render(<ChatMessage mensaje={msg} />);

    expect(
      screen.getByText(/Ley Organica de la Justicia Militar · LOJM 3/),
    ).toBeTruthy();
  });

  it("cae a la referencia del slug si no hay enriquecimiento", () => {
    const msg = {
      ...mensaje("resp", "bot"),
      fragmentos: [
        {
          id: 5,
          norma_id: 1,
          obra_id: null,
          texto: "Art. 3 ...",
          referencia: "LOJM 3",
          nivel_jerarquico: 4,
        },
      ],
      scores: [0.9],
    };
    render(<ChatMessage mensaje={msg} />);

    expect(screen.getByText("LOJM 3")).toBeTruthy();
  });

  it("no duplica la abreviatura cuando nombre == abreviatura", () => {
    const msg = {
      ...mensaje("resp", "bot"),
      fragmentos: [
        {
          id: 5,
          norma_id: 4,
          obra_id: null,
          texto: "Art. 3 ...",
          referencia: "LOJM 3",
          nivel_jerarquico: 4,
          norma_nombre: "LOJM",
          norma_abreviatura: "LOJM",
        },
      ],
      scores: [0.9],
    };
    render(<ChatMessage mensaje={msg} />);

    // Muestra solo "LOJM 3", nunca "LOJM · LOJM 3".
    expect(screen.getByText("LOJM 3")).toBeTruthy();
    expect(screen.queryByText(/LOJM · LOJM/)).toBeNull();
  });
});
