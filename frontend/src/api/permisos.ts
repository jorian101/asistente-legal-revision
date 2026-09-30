// Cliente HTTP para el sistema de módulos y permisos CRUD por usuario.
//
// Fase 2 del plan `plan/permisos-crud-modulos`:
// - GET /auth/permisos — permisos efectivos del usuario logueado (sidebar).
// - GET /admin/modulos — catálogo fijo de módulos (admin).
// - PATCH /admin/modulos/{clave} — editar metadata (admin).
// - GET /admin/usuarios/{carnet}/permisos — override + efectivo de un usuario.
// - PUT /admin/usuarios/{carnet}/permisos — reemplazar overrides (admin).

import { api } from "./auth";

export interface PermisoEfectivo {
  puede_crear: boolean;
  puede_leer: boolean;
  puede_actualizar: boolean;
  puede_eliminar: boolean;
}

/** Override de permisos del usuario: null = seguir default del rol. */
export interface PermisoOverrideDTO {
  puede_crear: boolean | null;
  puede_leer: boolean | null;
  puede_actualizar: boolean | null;
  puede_eliminar: boolean | null;
}

export interface UsuarioPermisosDTO {
  id: number;
  carnet: string;
  nombre: string;
  rol: string;
  cargo: string;
  activo: boolean;
}

/** Módulo que un usuario ve en su menú (activo + permiso de leer). */
export interface ModuloVisibleDTO {
  clave: string;
  nombre: string;
  descripcion: string;
  ruta: string;
}

/** GET /admin/modulos-visibles — módulos efectivos por usuario y por rol. */
export interface ModulosVisiblesDTO {
  por_usuario: Record<string, ModuloVisibleDTO[]>;
  por_rol: Record<string, ModuloVisibleDTO[]>;
}

export async function obtenerModulosVisibles(): Promise<ModulosVisiblesDTO> {
  const { data } = await api.get<ModulosVisiblesDTO>("/admin/modulos-visibles");
  return data;
}

/** GET /admin/usuarios — lista de usuarios para el selector de permisos. */
export async function listarUsuarios(): Promise<UsuarioPermisosDTO[]> {
  const { data } = await api.get<UsuarioPermisosDTO[]>("/admin/usuarios");
  return data;
}

// GET /auth/permisos — módulos activos con permisos efectivos del usuario.
export interface ModuloPermisoDTO extends PermisoEfectivo {
  clave: string;
  nombre: string;
  descripcion: string;
  ruta: string;
  orden: number;
}

export interface ModuloDTO {
  clave: string;
  nombre: string;
  descripcion: string;
  ruta: string;
  orden: number;
  activo: boolean;
}

export interface PermisoModuloDetalleDTO {
  clave: string;
  nombre: string;
  override: PermisoOverrideDTO;
  efectivo: PermisoEfectivo;
  /** Lo que otorga el rol sin override. */
  default_rol: PermisoEfectivo;
}

/** GET /auth/permisos — permisos efectivos del usuario logueado. */
export async function obtenerPermisosPropios(): Promise<ModuloPermisoDTO[]> {
  const { data } = await api.get<ModuloPermisoDTO[]>("/auth/permisos");
  return data;
}

/** GET /admin/modulos — catálogo fijo de módulos. */
export async function listarModulos(): Promise<ModuloDTO[]> {
  const { data } = await api.get<ModuloDTO[]>("/admin/modulos");
  return data;
}

/** PATCH /admin/modulos/{clave} — editar metadata de un módulo. */
export async function actualizarModulo(
  clave: string,
  campos: Partial<
    Pick<ModuloDTO, "nombre" | "descripcion" | "ruta" | "orden" | "activo">
  >,
): Promise<ModuloDTO> {
  const { data } = await api.patch<ModuloDTO>(
    `/admin/modulos/${clave}`,
    campos,
  );
  return data;
}

/** GET /admin/usuarios/{carnet}/permisos — override + efectivo de un usuario. */
export async function listarPermisosUsuario(
  carnet: string,
): Promise<PermisoModuloDetalleDTO[]> {
  const { data } = await api.get<PermisoModuloDetalleDTO[]>(
    `/admin/usuarios/${carnet}/permisos`,
  );
  return data;
}

/** PUT /admin/usuarios/{carnet}/permisos — reemplazar overrides. */
export async function asignarPermisosUsuario(
  carnet: string,
  permisos: Record<string, PermisoOverrideDTO>,
): Promise<void> {
  await api.put(`/admin/usuarios/${carnet}/permisos`, { permisos });
}
