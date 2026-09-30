// Test de la matriz de módulos por rol (config/modulosPorRol.ts).
//
// Valida la matriz de acceso mostrada en el gestor de usuarios: cada rol
// accede exactamente a los módulos que el backend autorizada (require_admin,
// require_consulta_user) y que el marco-practico Tabla 18 describe.

import { describe, it, expect } from "vitest";

import { modulosAccesoParaRol, modulosParaRol } from "../config/modulosPorRol";

describe("modulosAccesoParaRol", () => {
  it("administrador accede solo a módulos admin", () => {
    const labels = modulosAccesoParaRol("administrador").map((m) => m.label);
    expect(labels).toEqual([
      "Usuarios",
      "Corpus jurídico",
      "Dashboard",
      "Sala de Control",
      "Auditoría",
      "Consultas RAG",
      "Módulos",
      "Permisos",
      "Criterios",
      "Formatos TSJM",
    ]);
  });

  it("supervisor accede a expedientes + obrados + consulta + conversaciones", () => {
    const labels = modulosAccesoParaRol("supervisor").map((m) => m.label);
    expect(labels).toContain("Expedientes");
    expect(labels).toContain("Consultar");
    expect(labels).toContain("Conversaciones");
    expect(labels).toContain("Obrados generados");
    // Supervisor NO tiene Chats privados (módulo eliminado).
    expect(labels).not.toContain("Chats privados");
  });

  it("operador_juridico accede a obrados + consulta + expedientes", () => {
    const labels = modulosAccesoParaRol("operador_juridico").map(
      (m) => m.label,
    );
    expect(labels).toContain("Obrados generados");
    expect(labels).toContain("Consultar");
    expect(labels).toContain("Expedientes");
    // Dos módulos no comparten etiqueta: se confundían en el gestor de usuarios.
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("rol null devuelve lista vacia", () => {
    expect(modulosAccesoParaRol(null)).toEqual([]);
  });

  it("rol desconocido devuelve lista vacia", () => {
    expect(modulosAccesoParaRol("rol-inventado")).toEqual([]);
  });
});

describe("modulosParaRol (sidebar /asistente)", () => {
  it("supervisor: expedientes primero (su caso de uso)", () => {
    const to = modulosParaRol("supervisor").map((m) => m.to);
    expect(to[0]).toBe("/asistente/expedientes");
  });

  it("operador_juridico: expedientes primero (landing inicial, fix bug F0.6)", () => {
    const to = modulosParaRol("operador_juridico").map((m) => m.to);
    expect(to[0]).toBe("/asistente/expedientes");
  });
});
