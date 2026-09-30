// Módulos del asistente, por rol.
//
// Dos consumidores:
// 1. MODULOS_POR_ROL + modulosParaRol — sidebar /asistente/* (ConsultaLayout
//    y Router). Solo módulos de consulta; el rol administrador no llega aquí.
// 2. MODULOS_MATRIZ + modulosAccesoParaRol — gestor de usuarios (Usuarios.tsx):
//    muestra QUÉ módulos accede cada rol. Incluye módulos admin + consulta,
//    espejando los guards del backend (require_permiso por módulo y operación).
//
// Marco-practico Tabla 18 (§2573-2576):
// - Administrador: gestión técnica global (usuarios, corpus, métricas).
// - Supervisor: apertura de expedientes + consulta/obrados concluidos.
// - Operador jurídico: consulta + borradores + publicación (RF-16/17/19/20,21).

export type Rol = "administrador" | "supervisor" | "operador_juridico";

export interface Modulo {
  to: string;
  label: string;
  descripcion: string;
  color?: "green" | "blue" | "orange";
  icono?: import("lucide-react").LucideIcon;
}

// --- Módulos de consulta (sidebar /asistente/*) ---

const CONSULTAR: Modulo = {
  to: "/asistente/consultar",
  label: "Consultar",
  descripcion: "Consulta jurídica RAG",
  color: "orange",
};

const CONVERSACIONES: Modulo = {
  to: "/asistente/conversaciones",
  label: "Conversaciones",
  descripcion: "Historial de consultas del chat",
  color: "orange",
};

const EXPEDIENTES: Modulo = {
  to: "/asistente/expedientes",
  label: "Expedientes",
  descripcion: "Apertura y gestión de expedientes",
  color: "blue",
};

// Obras (obrados): carga/publicación/eliminación dentro del detalle de
// expediente. Sin página propia: espeja el módulo 'obras' del backend
// para el gestor de usuarios. Operador full (Regla 5 por propietario);
// editar expediente sigue siendo solo-supervisor.
const OBRAS: Modulo = {
  to: "/asistente/expedientes",
  label: "Obrados del expediente",
  descripcion: "Carga y gestión de obrados del expediente",
  color: "blue",
};

const BORRADORES: Modulo = {
  to: "/asistente/borradores",
  label: "Obrados generados",
  descripcion: "Obrados generados en el TSJM",
};

// --- Módulos de administración (bounded context admin) ---

const USUARIOS: Modulo = {
  to: "/admin/usuarios",
  label: "Usuarios",
  descripcion: "Gestión de usuarios y perfiles",
  color: "green",
};

const CORPUS: Modulo = {
  to: "/admin/corpus",
  label: "Corpus jurídico",
  descripcion: "Indexación y configuración de normativa",
  color: "green",
};

const METRICAS: Modulo = {
  to: "/admin/metricas",
  label: "Dashboard",
  descripcion: "Resumen general de chats y modelos",
  color: "green",
};

const SALA_CONTROL: Modulo = {
  to: "/admin/sala-control",
  label: "Sala de Control",
  descripcion: "Trazabilidad del pipeline RAG en vivo",
  color: "green",
};

const AUDITORIA: Modulo = {
  to: "/admin/auditoria",
  label: "Auditoría",
  descripcion: "Log de acciones sensitivas (R6)",
  color: "green",
};

const CONSULTAS_HISTORIAL: Modulo = {
  to: "/admin/consultas",
  label: "Consultas RAG",
  descripcion: "Auditoría del historial de consultas con filtros",
  color: "green",
};

const MODULOS: Modulo = {
  to: "/admin/modulos",
  label: "Módulos",
  descripcion: "Catálogo de módulos y su configuración",
  color: "green",
};

const PERMISOS: Modulo = {
  to: "/admin/permisos",
  label: "Permisos",
  descripcion: "Permisos CRUD por módulo y usuario",
  color: "green",
};

const DOCTRINA: Modulo = {
  to: "/asistente/doctrina",
  label: "Fuentes",
  descripcion: "Normas, jurisprudencia y doctrina",
  color: "blue",
};

const CRITERIOS: Modulo = {
  to: "/admin/criterios",
  label: "Criterios",
  descripcion: "Criterios del asistente (solo admin)",
  color: "green",
};

const FORMATOS: Modulo = {
  to: "/admin/formatos",
  label: "Formatos TSJM",
  descripcion: "Layouts de obrados TSJM",
  color: "green",
};

// Formatos para el supervisor: la página vive en /asistente/formatos (el
// catálogo backend la registra en /admin/formatos, ver rutaFrontend).
const FORMATOS_ASISTENTE: Modulo = { ...FORMATOS, to: "/asistente/formatos" };

// Sidebar del asistente (no incluye módulos admin).
export const MODULOS_POR_ROL: Record<Rol, Modulo[]> = {
  // Supervisor: expedientes al frente + obrados (genera y gestiona),
  // luego consulta/conversaciones + doctrina (aprobaciones).
  supervisor: [
    EXPEDIENTES,
    BORRADORES,
    DOCTRINA,
    CONSULTAR,
    CONVERSACIONES,
    FORMATOS_ASISTENTE,
  ],
  // Operador jurídico: expedientes al frente como ventana inicial (lista filtrada por
  // propietario_id vía backend GET /expedientes/). Consultas y borradores operan
  // sobre expedientes del usuario. Fix del bug reportado en F0.6 (Borradores.tsx:284
  // exigia ID manual sin acceso a lista).
  operador_juridico: [
    EXPEDIENTES,
    BORRADORES,
    DOCTRINA,
    CONSULTAR,
    CONVERSACIONES,
  ],
  // Admin no usa el sidebar del asistente (ProtectedRoute lo redirige a /admin).
  administrador: [],
};

// Matriz completa de acceso por rol (gestor de usuarios, dashboard futuro).
// Espeja el backend: admin → require_admin; super+operador → require_consulta_user;
// borradores → operador_juridico (RF-16/17/19/20/21, Tabla 18).
export const MODULOS_MATRIZ: Record<Rol, Modulo[]> = {
  administrador: [
    USUARIOS,
    CORPUS,
    METRICAS,
    SALA_CONTROL,
    AUDITORIA,
    CONSULTAS_HISTORIAL,
    MODULOS,
    PERMISOS,
    CRITERIOS,
    FORMATOS,
  ],
  supervisor: [
    EXPEDIENTES,
    OBRAS,
    BORRADORES,
    DOCTRINA,
    CONSULTAR,
    CONVERSACIONES,
    FORMATOS,
  ],
  operador_juridico: [
    EXPEDIENTES,
    OBRAS,
    BORRADORES,
    DOCTRINA,
    CONSULTAR,
    CONVERSACIONES,
  ],
};

export function modulosParaRol(rol: string | null): Modulo[] {
  if (rol === null) return [];
  return MODULOS_POR_ROL[rol as Rol] ?? [];
}

export function modulosAccesoParaRol(rol: string | null): Modulo[] {
  if (rol === null) return [];
  return MODULOS_MATRIZ[rol as Rol] ?? [];
}

// --- Sidebar dinámico por permisos (Fase 2 plan permisos-crud-modulos) ---
//
// El backend GET /auth/permisos devuelve los módulos activos con permisos
// efectivos del usuario. El sidebar se construye desde ahí. Estos helpers
// mapean ModuloPermisoDTO → Modulo y filtran por operación "leer" (ver el
// módulo en el sidebar) o "crear" (por si algún día el sidebar necesita
// distinguir). Mientras los permisos cargan (null), se usa la matriz por rol
// como fallback.

import type { ModuloPermisoDTO } from "../api/permisos";
import {
  Activity,
  BookOpen,
  Brain,
  Database,
  FileText,
  FolderOpen,
  History,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  Scale,
  Search,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

// Íconos por clave de módulo (catálogo backend). Fuente única para sidebar
// y dashboard. Fallback: LayoutGrid.
export const ICONO_POR_CLAVE: Record<string, LucideIcon> = {
  usuarios: Users,
  corpus: BookOpen,
  metricas: LayoutDashboard,
  sala_control: Activity,
  auditoria: ShieldCheck,
  consultas_rag: Database,
  modulos: LayoutGrid,
  permisos: KeyRound,
  expedientes: FolderOpen,
  consultar: Search,
  conversaciones: History,
  borradores: FileText,
  doctrina: Scale,
  criterios: Brain,
  formatos: FileText,
};

export function iconoParaClave(clave: string): LucideIcon {
  return ICONO_POR_CLAVE[clave] ?? LayoutGrid;
}

// Módulos de CAPACIDAD del catálogo backend que no tienen página propia en el
// frontend (ej. 'chats' vive embebido en /asistente/consultar). El backend los
// expone con puede_leer (los guards de /chats/* lo requieren), pero el
// sidebar/dashboard no deben renderizar un link a una ruta inexistente.
export const MODULOS_SIN_PAGINA: ReadonlySet<string> = new Set(["chats"]);

const COLOR_POR_RUTA: Record<string, Modulo["color"]> = {
  "/admin/": "green",
  "/asistente/expedientes": "blue",
  "/asistente/borradores": "blue",
};

function colorParaRuta(ruta: string): Modulo["color"] {
  for (const [prefijo, color] of Object.entries(COLOR_POR_RUTA)) {
    if (ruta.startsWith(prefijo)) return color;
  }
  return "orange";
}

// Formatos se registra en /admin/formatos en el catálogo (BD), pero el
// supervisor lo usa desde el área del asistente: se sirve también en
// /asistente/formatos. Solo el área del asistente lo remapea.
export function rutaFrontend(
  p: ModuloPermisoDTO,
  area: "admin" | "asistente",
): string {
  return area === "asistente" && p.clave === "formatos"
    ? "/asistente/formatos"
    : p.ruta;
}

export function moduloDesdePermiso(
  p: ModuloPermisoDTO,
  area: "admin" | "asistente" = p.ruta.startsWith("/admin/")
    ? "admin"
    : "asistente",
): Modulo {
  return {
    to: rutaFrontend(p, area),
    label: p.nombre,
    descripcion: p.descripcion,
    color: colorParaRuta(p.ruta),
    icono: iconoParaClave(p.clave),
  };
}

// ¿El módulo pertenece al área? Formatos (ruta /admin/) también es del
// asistente: el supervisor lo usa desde /asistente/formatos.
export function esDeArea(
  p: ModuloPermisoDTO,
  area: "admin" | "asistente",
): boolean {
  return area === "admin"
    ? p.ruta.startsWith("/admin/")
    : p.ruta.startsWith("/asistente/") || p.clave === "formatos";
}

export function modulosDesdePermisos(
  permisos: ModuloPermisoDTO[] | null,
  area?: "admin" | "asistente",
): Modulo[] {
  if (permisos === null) return [];
  // Dedupe por ruta: módulos de capacidad distintos pueden apuntar a la misma
  // página (ej. 'obras' espeja la ruta de 'expedientes'); el sidebar no debe
  // renderizar entradas duplicadas. Gana el de menor orden (tras sort).
  const rutasVistas = new Set<string>();
  const modulos: Modulo[] = [];
  for (const p of [...permisos]
    .filter((p) => p.puede_leer)
    .filter((p) => !MODULOS_SIN_PAGINA.has(p.clave))
    .sort((a, b) => a.orden - b.orden)) {
    if (rutasVistas.has(p.ruta)) continue;
    rutasVistas.add(p.ruta);
    modulos.push(moduloDesdePermiso(p, area));
  }
  return modulos;
}

// --- Dashboard: módulos del área como cards navegables ---

export function modulosDashboardArea(
  permisos: ModuloPermisoDTO[] | null,
  area: "admin" | "asistente",
): Modulo[] {
  if (permisos === null) return [];
  return modulosDesdePermisos(
    permisos.filter((p) => esDeArea(p, area)),
    area,
  );
}

// --- Etiquetas legibles de rol (para headers, mensajes, tablas) ---

export const ROL_LABEL: Record<Rol, string> = {
  administrador: "Administrador",
  supervisor: "Supervisor",
  operador_juridico: "Operador Jurídico",
};

export function labelRol(rol: string | null | undefined): string {
  if (rol === null || rol === undefined) return "—";
  return ROL_LABEL[rol as Rol] ?? rol;
}
