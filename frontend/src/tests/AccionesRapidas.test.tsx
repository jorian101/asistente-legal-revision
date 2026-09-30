// AccionesRapidas: atajos que rellenan la consulta (no la envían) con el tipo forzado.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccionesRapidas } from "../components/chat/AccionesRapidas";

describe("AccionesRapidas", () => {
  it("el dictamen de fondo fuerza su tipo de respuesta", async () => {
    const onElegir = vi.fn();
    render(<AccionesRapidas onElegirConsulta={onElegir} />);

    await userEvent.click(
      screen.getByRole("button", { name: /dictamen de fondo/i }),
    );

    expect(onElegir).toHaveBeenCalledWith(
      expect.stringContaining("dictamen de fondo"),
      "dictamen_fondo",
    );
  });

  it("el auto de vista pre-llena la consulta sin forzar tipo", async () => {
    const onElegir = vi.fn();
    render(<AccionesRapidas onElegirConsulta={onElegir} />);

    await userEvent.click(
      screen.getByRole("button", { name: /auto de vista/i }),
    );

    expect(onElegir).toHaveBeenCalledWith(
      expect.stringContaining("auto de vista"),
      undefined,
    );
  });

  it("la relación de obrados usa el tipo relacion_obrados", async () => {
    const onElegir = vi.fn();
    render(<AccionesRapidas onElegirConsulta={onElegir} />);

    await userEvent.click(
      screen.getByRole("button", { name: /relación de obrados/i }),
    );

    expect(onElegir.mock.calls[0][1]).toBe("relacion_obrados");
  });

  it("deshabilitado bloquea todos los atajos", () => {
    render(<AccionesRapidas onElegirConsulta={vi.fn()} deshabilitado />);

    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
