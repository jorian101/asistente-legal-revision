// Cargos institucionales por rol (marco-practico Tabla 18).
//
// Fuente de verdad: backend/src/domain/entities/usuario.py (CARGOS_POR_ROL).
// El administrador es personal tecnico/TI (no pertenece a la SAC). Sin
// "Otro": los cargos fuera de la SAC se agregaran cuando esos perfiles
// accedan al asistente.

export type RolCargo = "administrador" | "supervisor" | "operador_juridico";

export const CARGOS_POR_ROL: Record<RolCargo, readonly string[]> = {
  administrador: ["Personal Técnico"],
  operador_juridico: [
    "Auditor",
    "Fiscal",
    "Vocal Relator",
    "Secretaria de Cámara",
  ],
  supervisor: ["Vocal Presidente", "Auxiliar de Secretaría de Cámara"],
};

export function cargosParaRol(rol: string | null): readonly string[] {
  if (rol === null) return [];
  return CARGOS_POR_ROL[rol as RolCargo] ?? [];
}
