// Test SelectOtro: select de catálogo con opción "Otro" que abre input libre.
//
// Verifica:
// - Elegir un valor del catálogo dispara onChange con ese valor.
// - Elegir "Otro" limpia el input y lo enfoca para escribir libre.
// - Un valor legacy (no catalogado) se muestra como "Otro" con el texto.
// - Escribir en el input de "Otro" propaga onChange con texto libre.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, it, expect, vi } from "vitest";

import { SelectOtro, VALOR_OTRO } from "../components/ui/SelectOtro";

const OPCIONES = [
  { valor: "desercion", label: "Deserción" },
  { valor: "hurto", label: "Hurto" },
  { valor: "robo", label: "Robo" },
];

function renderSelectOtro({
  value = "",
  onChange = vi.fn(),
  required = false,
}: {
  value?: string;
  onChange?: (v: string) => void;
  required?: boolean;
} = {}) {
  return render(
    <SelectOtro
      id="delito"
      label="Delito"
      opciones={OPCIONES}
      value={value}
      onChange={onChange}
      required={required}
    />,
  );
}

describe("SelectOtro", () => {
  it("muestra las opciones del catálogo", () => {
    renderSelectOtro();
    const select = screen.getByLabelText("Delito");
    expect(select).toBeInTheDocument();
  });

  it("elige un valor del catálogo y dispara onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderSelectOtro({ onChange });

    const select = screen.getByLabelText("Delito");
    await user.selectOptions(select, "hurto");

    expect(onChange).toHaveBeenCalledWith("hurto");
  });

  it('elige "Otro", limpia el valor y permite escribir libre', async () => {
    const user = userEvent.setup();
    // Wrapper controlado: refleja onChange como haría un formulario real.
    function Wrapper() {
      const [value, setValue] = React.useState("desercion");
      return (
        <SelectOtro
          id="delito"
          label="Delito"
          opciones={OPCIONES}
          value={value}
          onChange={setValue}
        />
      );
    }
    render(<Wrapper />);

    const select = screen.getByLabelText("Delito");
    await user.selectOptions(select, VALOR_OTRO);

    await waitFor(() => {
      const input = screen.getByRole("textbox", {
        name: "Delito (otro valor)",
      });
      expect(input).toBeInTheDocument();
    });

    const input = screen.getByRole("textbox", { name: "Delito (otro valor)" });
    await user.type(input, "Otro delito");
    expect(input).toHaveValue("Otro delito");
  });

  it("muestra un valor legacy (no catalogado) como 'Otro' con su texto", () => {
    renderSelectOtro({ value: "DELITO-ANTIGUO" });

    const select = screen.getByLabelText("Delito");
    expect(select).toHaveValue(VALOR_OTRO);
    const input = screen.getByRole("textbox", { name: "Delito (otro valor)" });
    expect(input).toHaveValue("DELITO-ANTIGUO");
  });
});
