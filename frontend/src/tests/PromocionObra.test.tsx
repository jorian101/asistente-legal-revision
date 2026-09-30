// Promoción de obrados a jurisprudencia desde el detalle del expediente:
// el operador propone; el supervisor promueve.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { PermisosContext } from "../context/usePermisos";
import { permisosDeTest } from "./helpers";
import { setAuthState } from "../api/auth";
import Expedientes from "../pages/consultas/Expedientes";
import type { AuthState } from "../api/auth";

vi.mock("../api/expedientes", () => ({
  abrirExpediente: vi.fn(),
  cambiarEstadoExpediente: vi.fn(),
  cargarObra: vi.fn(),
  editarExpediente: vi.fn(),
  eliminarObra: vi.fn(),
  getRequisitos: vi.fn(),
  listarExpedientes: vi.fn(),
  listarHistorialExpediente: vi.fn(),
  publicarObra: vi.fn(),
  proponerPromocion: vi.fn(),
  resolverPromocion: vi.fn(),
}));
vi.mock("../api/fuentes", async (orig) => ({
  ...(await orig<typeof import("../api/fuentes")>()),
  promoverObraANorma: vi.fn(),
  seleccionarFuente: vi.fn(),
  subirFuente: vi.fn(),
}));
vi.mock("../api/jobs", () => ({
  obtenerTrabajo: vi.fn(),
  cancelarTrabajo: vi.fn(),
}));
vi.mock("../lib/toasts", () => ({ toast: vi.fn() }));
vi.mock("../api/borradores", () => ({
  listarBorradores: vi.fn().mockResolvedValue([]),
  TIPO_BORRADOR_LABEL: {},
}));
vi.mock("../api/doctrina", () => ({
  listarDoctrinaPrivadaExpediente: vi.fn().mockResolvedValue([]),
  descargarObra: vi.fn(),
}));

import {
  eliminarObra,
  listarExpedientes,
  listarHistorialExpediente,
  proponerPromocion,
  publicarObra,
  resolverPromocion,
} from "../api/expedientes";
import {
  promoverObraANorma,
  seleccionarFuente,
  subirFuente,
} from "../api/fuentes";
import { cancelarTrabajo, obtenerTrabajo } from "../api/jobs";

// Permisos del render; un test puede denegar operaciones antes de renderizar.
let permisos = permisosDeTest();

const EXPEDIENTE = {
  id: 7,
  numero_caso: "9999",
  estado: "activo",
  creado_at_iso: "2026-01-01T00:00:00Z",
  tipo_proceso: "consulta",
  procesado_nombre: null,
  delito: null,
  tribunal_origen: null,
};

const obra = (extra: Record<string, unknown> = {}) => ({
  id: 5,
  expediente_id: 7,
  propietario_id: 3,
  tipo_documento: "sentencia",
  nombre_archivo: "sentencia.pdf",
  estado_visibilidad: "publicado",
  estado_procesamiento: "completado",
  es_propia: true,
  created_at_iso: "2026-01-02T00:00:00Z",
  estado_validacion: null,
  ...extra,
});

async function abrirDetalle(rol: "supervisor" | "operador_juridico") {
  const value: AuthState = {
    access_token: "t",
    rol,
    carnet: "1",
    nombre: "Prueba",
    id: 3,
  };
  setAuthState(value);
  render(
    <AuthProvider>
      <PermisosContext.Provider value={permisos}>
        <MemoryRouter>
          <Expedientes />
        </MemoryRouter>
      </PermisosContext.Provider>
    </AuthProvider>,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: /ver expediente 9999/i }),
  );
}

beforeEach(() => {
  permisos = permisosDeTest();
  vi.clearAllMocks();
  (listarExpedientes as ReturnType<typeof vi.fn>).mockResolvedValue({
    items: [EXPEDIENTE],
    total: 1,
    pagina: 1,
    por_pagina: 10,
  });
});

describe("promoción de un obrado a jurisprudencia", () => {
  it("el operador propone su obrado publicado", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra()],
      total: 1,
    });
    (proponerPromocion as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", {
        name: /proponer como jurisprudencia/i,
      }),
    );

    await waitFor(() => expect(proponerPromocion).toHaveBeenCalledWith(7, 5));
  });

  it("no ofrece proponer si ya está pendiente ni si no está publicado", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [
        obra({ id: 5, estado_validacion: "promocion_pendiente" }),
        obra({ id: 6, estado_visibilidad: "privado" }),
      ],
      total: 2,
    });
    await abrirDetalle("operador_juridico");

    await screen.findByText("Propuesto a jurisprudencia");
    expect(
      screen.queryByRole("button", { name: /proponer como jurisprudencia/i }),
    ).toBeNull();
  });

  it("el supervisor promueve un obrado publicado", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra({ es_propia: false })],
      total: 1,
    });
    (resolverPromocion as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("supervisor");

    await userEvent.click(
      await screen.findByRole("button", { name: /promover a jurisprudencia/i }),
    );

    await waitFor(() =>
      expect(resolverPromocion).toHaveBeenCalledWith(7, 5, true),
    );
  });
});

describe("promoción de un obrado a norma", () => {
  it("el operador propone la promoción indicando nombre y jerarquía", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra()],
      total: 1,
    });
    (promoverObraANorma as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "jn1",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "jn1",
      tipo: "obra_a_norma",
      estado: "completado",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: "2026-09-22T00:00:05Z",
      error: null,
      resultado: { norma_id: 9 },
    });
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Proponer como norma" }),
    );
    await userEvent.type(
      screen.getByLabelText("Nombre de la norma"),
      "Ley de recursos",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Jerarquía"),
      "militar",
    );
    await userEvent.click(screen.getByRole("button", { name: "Proponer" }));

    await waitFor(() =>
      expect(promoverObraANorma).toHaveBeenCalledWith(
        5,
        "Ley de recursos",
        "militar",
      ),
    );
    // Al completar el trabajo, el modal se cierra (limpia el nombre).
    await waitFor(() =>
      expect(screen.queryByLabelText("Nombre de la norma")).toBeNull(),
    );
  });

  it("mientras indexa se puede cancelar", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra()],
      total: 1,
    });
    (promoverObraANorma as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "jn2",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "jn2",
      tipo: "obra_a_norma",
      estado: "en_curso",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: null,
      error: null,
      resultado: null,
    });
    (cancelarTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Proponer como norma" }),
    );
    await userEvent.type(
      screen.getByLabelText("Nombre de la norma"),
      "Ley de recursos",
    );
    await userEvent.click(screen.getByRole("button", { name: "Proponer" }));

    await userEvent.click(
      await screen.findByRole("button", { name: "Cancelar indexado" }),
    );
    await waitFor(() => expect(cancelarTrabajo).toHaveBeenCalledWith("jn2"));
  });

  it("no ofrece promover a norma lo ya promovido y muestra su insignia", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra({ estado_validacion: "promovida_a_norma" })],
      total: 1,
    });
    await abrirDetalle("operador_juridico");

    expect(await screen.findByText("Norma")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /(promover a|proponer como) norma/i,
      }),
    ).toBeNull();
  });
});

describe("publicar y eliminar obrados (caracterización)", () => {
  it("publica un obrado propio y privado tras confirmar", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra({ estado_visibilidad: "privado" })],
      total: 1,
    });
    (publicarObra as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Publicar" }),
    );
    const dialogo = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialogo).getByRole("button", { name: "Publicar" }),
    );

    await waitFor(() => expect(publicarObra).toHaveBeenCalledWith(7, 5));
  });

  it("elimina un obrado propio tras confirmar", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra()],
      total: 1,
    });
    (eliminarObra as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "Eliminar" }),
    );
    const dialogo = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialogo).getByRole("button", { name: "Eliminar" }),
    );

    await waitFor(() => expect(eliminarObra).toHaveBeenCalledWith(7, 5));
  });

  it("el obrado ajeno no se puede publicar ni eliminar", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra({ es_propia: false, estado_visibilidad: "privado" })],
      total: 1,
    });
    await abrirDetalle("operador_juridico");

    await screen.findByText("sentencia.pdf");
    expect(screen.queryByRole("button", { name: "Publicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
  });
});

describe("acciones de obrados según permisos efectivos", () => {
  it("sin obras.eliminar ni obras.actualizar no ofrece eliminar, publicar ni proponer", async () => {
    permisos = permisosDeTest(["obras.eliminar", "obras.actualizar"]);
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra(), obra({ id: 6, estado_visibilidad: "privado" })],
      total: 2,
    });
    await abrirDetalle("operador_juridico");

    await screen.findAllByRole("button", { name: "Descargar" });
    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Publicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: /proponer como/i })).toBeNull();
  });

  it("sin obras.crear no muestra el formulario de carga", async () => {
    permisos = permisosDeTest(["obras.crear"]);
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [obra()],
      total: 1,
    });
    await abrirDetalle("operador_juridico");

    await screen.findAllByRole("button", { name: "Descargar" });
    expect(screen.queryByRole("button", { name: "Cargar obrado" })).toBeNull();
  });
});

describe("subir doctrina (libro) desde el detalle del expediente", () => {
  it("al terminar el indexado, fija el libro al expediente", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [],
      total: 0,
    });
    (subirFuente as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "j1",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "j1",
      tipo: "fuente",
      estado: "completado",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: "2026-09-22T00:00:05Z",
      error: null,
      resultado: { norma_id: 42 },
    });
    (seleccionarFuente as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "+ Subir doctrina (libro)" }),
    );
    const form = screen.getByRole("form", { name: /subir doctrina/i });
    await userEvent.upload(
      within(form).getByLabelText(/archivo/i),
      new File(["x"], "libro.pdf", { type: "application/pdf" }),
    );
    await userEvent.type(
      within(form).getByLabelText("Nombre"),
      "Libro de test",
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Subir como privada" }),
    );

    await waitFor(() => expect(seleccionarFuente).toHaveBeenCalledWith(42, 7));
    // El formulario se cierra al terminar (libroSubido oculta subirDoctrinaVisible).
    expect(screen.queryByRole("form", { name: /subir doctrina/i })).toBeNull();
  });

  it("si el trabajo completa sin norma_id, no llama a fijar la fuente", async () => {
    (listarHistorialExpediente as ReturnType<typeof vi.fn>).mockResolvedValue({
      expediente_id: 7,
      obras: [],
      total: 0,
    });
    (subirFuente as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "j2",
      estado: "en_curso",
    });
    (obtenerTrabajo as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "j2",
      tipo: "fuente",
      estado: "completado",
      cancelacion_solicitada: false,
      iniciado_en: "2026-09-22T00:00:00Z",
      terminado_en: "2026-09-22T00:00:05Z",
      error: null,
      resultado: null,
    });
    await abrirDetalle("operador_juridico");

    await userEvent.click(
      await screen.findByRole("button", { name: "+ Subir doctrina (libro)" }),
    );
    const form = screen.getByRole("form", { name: /subir doctrina/i });
    await userEvent.upload(
      within(form).getByLabelText(/archivo/i),
      new File(["x"], "libro.pdf", { type: "application/pdf" }),
    );
    await userEvent.type(
      within(form).getByLabelText("Nombre"),
      "Libro de test",
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Subir como privada" }),
    );

    await waitFor(() => expect(obtenerTrabajo).toHaveBeenCalled());
    expect(seleccionarFuente).not.toHaveBeenCalled();
  });
});
