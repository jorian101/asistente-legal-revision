// Test de helpers de permisos efectivos → sidebar (config/modulosPorRol.ts).

import { describe, it, expect } from "vitest";

import {
  moduloDesdePermiso,
  modulosDesdePermisos,
} from "../config/modulosPorRol";
import type { ModuloPermisoDTO } from "../api/permisos";

function permiso(overrides: Partial<ModuloPermisoDTO>): ModuloPermisoDTO {
  return {
    clave: "consultar",
    nombre: "Consultar",
    descripcion: "Consulta jurídica RAG",
    ruta: "/asistente/consultar",
    orden: 10,
    puede_crear: true,
    puede_leer: true,
    puede_actualizar: true,
    puede_eliminar: true,
    ...overrides,
  };
}

describe("modulosDesdePermisos", () => {
  it("filtra módulos sin permiso de lectura", () => {
    const permisos: ModuloPermisoDTO[] = [
      permiso({
        clave: "consultar",
        puede_leer: true,
        ruta: "/asistente/consultar",
        orden: 2,
      }),
      permiso({
        clave: "borradores",
        puede_leer: false,
        ruta: "/asistente/borradores",
        orden: 1,
      }),
    ];

    const modulos = modulosDesdePermisos(permisos);

    expect(modulos.map((m) => m.to)).toEqual(["/asistente/consultar"]);
  });

  it("ordena por orden del catálogo", () => {
    const permisos: ModuloPermisoDTO[] = [
      permiso({ clave: "borradores", ruta: "/asistente/borradores", orden: 3 }),
      permiso({
        clave: "expedientes",
        ruta: "/asistente/expedientes",
        orden: 1,
      }),
      permiso({ clave: "consultar", ruta: "/asistente/consultar", orden: 2 }),
    ];

    const modulos = modulosDesdePermisos(permisos);

    expect(modulos.map((m) => m.to)).toEqual([
      "/asistente/expedientes",
      "/asistente/consultar",
      "/asistente/borradores",
    ]);
  });

  it("permisos null devuelve lista vacia (fallback a cargo del layout)", () => {
    expect(modulosDesdePermisos(null)).toEqual([]);
  });

  it("excluye modulos de capacidad sin pagina (chats embebido en consultar)", () => {
    const permisos: ModuloPermisoDTO[] = [
      permiso({
        clave: "consultar",
        ruta: "/asistente/consultar",
        orden: 1,
      }),
      permiso({
        clave: "chats",
        ruta: "/asistente/chats",
        orden: 2,
      }),
    ];

    const modulos = modulosDesdePermisos(permisos);

    expect(modulos.map((m) => m.to)).toEqual(["/asistente/consultar"]);
  });

  it("deduplica entradas con la misma ruta (obras espeja expedientes)", () => {
    const permisos: ModuloPermisoDTO[] = [
      permiso({
        clave: "expedientes",
        nombre: "Expedientes",
        ruta: "/asistente/expedientes",
        orden: 7,
      }),
      permiso({
        clave: "obras",
        nombre: "Obras",
        descripcion: "Carga y gestión de obrados del expediente",
        ruta: "/asistente/expedientes",
        orden: 16,
      }),
    ];

    const modulos = modulosDesdePermisos(permisos);

    expect(modulos).toHaveLength(1);
    expect(modulos[0].to).toBe("/asistente/expedientes");
    expect(modulos[0].label).toBe("Expedientes");
  });

  it("mapea ruta admin a color green", () => {
    const m = moduloDesdePermiso(
      permiso({ clave: "corpus", ruta: "/admin/corpus", orden: 2 }),
    );
    expect(m.color).toBe("green");
  });
});
