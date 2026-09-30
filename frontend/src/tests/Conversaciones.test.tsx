// Test Conversaciones: cards del historial de chat con modos y CRUD.
// Usa chatStore real (localStorage) y un probe de ubicacion para validar
// la navegacion "Ver".

import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import Conversaciones from "../pages/consultas/Conversaciones";
import { chatStore } from "../lib/chatStore";
import { AuthProvider } from "../context/AuthContext";
import { setAuthState } from "../api/auth";
import type { AuthState } from "../api/auth";

const USUARIO = 29;

function Ubicacion() {
  const loc = useLocation();
  return <span data-testid="ubicacion">{loc.pathname + loc.search}</span>;
}

function renderConversaciones() {
  const value: AuthState = {
    access_token: "test-token",
    rol: "operador_juridico",
    carnet: "1001",
    nombre: "Operador de Prueba",
    id: USUARIO,
  };
  setAuthState(value);
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/asistente/conversaciones"]}>
        <Routes>
          <Route
            path="/asistente/conversaciones"
            element={
              <>
                <Conversaciones />
                <Ubicacion />
              </>
            }
          />
          <Route path="/asistente/consultar" element={<Ubicacion />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("Conversaciones", () => {
  it("muestra estado vacio sin conversaciones", () => {
    renderConversaciones();
    expect(
      screen.getByText(/no hay conversaciones todav/i),
    ).toBeInTheDocument();
  });

  it("lista las conversaciones como cards y 'Ver' navega al chat", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Caso A");
    chatStore.crearConversacion(USUARIO, "Caso B");
    renderConversaciones();

    expect(screen.getByText("Caso A")).toBeInTheDocument();
    expect(screen.getByText("Caso B")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Caso A"));
    expect(screen.getByTestId("ubicacion").textContent).toBe(
      `/asistente/consultar?chat=${conv.id}`,
    );
  });

  it("renombra inline desde el menu", () => {
    const conv = chatStore.crearConversacion(USUARIO, "Original");
    renderConversaciones();

    fireEvent.click(
      screen.getByRole("button", { name: "Opciones de Original" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /renombrar/i }));

    const input = screen.getByRole("textbox", {
      name: "Nombre de la conversacion",
    });
    fireEvent.change(input, { target: { value: "Renombrado" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const actual = chatStore
      .listarConversaciones(USUARIO)
      .find((c) => c.id === conv.id);
    expect(actual?.titulo).toBe("Renombrado");
  });

  it("elimina con soft delete tras confirmar en el dialog", () => {
    const conv = chatStore.crearConversacion(USUARIO, "A eliminar");
    renderConversaciones();

    fireEvent.click(
      screen.getByRole("button", { name: "Opciones de A eliminar" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Eliminar" }));

    expect(
      chatStore.listarConversaciones(USUARIO).some((c) => c.id === conv.id),
    ).toBe(false);
  });

  it("cambia a modo 'Por carpetas' y agrupa por carpeta", () => {
    const conv = chatStore.crearConversacion(USUARIO, "En carpeta");
    const carpeta = chatStore.crearEspacio(USUARIO, "Recursos");
    chatStore.moverACarpeta(USUARIO, conv.id, carpeta.id);
    renderConversaciones();

    fireEvent.click(screen.getByRole("button", { name: "Por carpetas" }));
    expect(screen.getByText(/recursos \(1\)/i)).toBeInTheDocument();
  });
});
