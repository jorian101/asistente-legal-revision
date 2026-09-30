// Cliente HTTP para asistente-legal.
//
// Regla 2 Trail of Bits:
// - Access token: 1h, en memoria JS (Authorization Bearer header).
// - Refresh token: 7d, cookie httpOnly/Secure/SameSite=Strict.
//   El navegador lo envía automaticamente a /auth/refresh (mismo origin, credentials: "include").
// - En 401, el interceptor intenta refresh una vez y rehace la request original.
//   Si refresh falla, redirige a /login.

import axios, {
  type AxiosError,
  type AxiosProgressEvent,
  type InternalAxiosRequestConfig,
} from "axios";

export interface AuthState {
  access_token: string | null;
  rol: string | null;
  carnet: string | null;
  nombre: string | null;
  id: number | null;
  /** Cargo institucional (Vocal Relator, Auditor…), para el header. */
  cargo?: string | null;
}

const STORAGE_KEY = "asistente-legal-auth";

export let authState: AuthState = loadAuthState();

function loadAuthState(): AuthState {
  // El access token vive SOLO en memoria (Regla 2): sessionStorage guarda el perfil
  // (rol, carnet, nombre, id) para saber que hay una sesion por restaurar tras un F5;
  // AuthProvider la restaura pidiendo /auth/refresh (cookie httpOnly).
  const vacio: AuthState = {
    access_token: null,
    rol: null,
    carnet: null,
    nombre: null,
    id: null,
  };
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return vacio;
    const parsed = JSON.parse(raw) as Partial<AuthState>;
    const perfil: AuthState = {
      access_token: null,
      rol: parsed.rol ?? null,
      carnet: parsed.carnet ?? null,
      nombre: parsed.nombre ?? null,
      id: parsed.id ?? null,
      cargo: parsed.cargo ?? null,
    };
    // Version anterior: guardaba el token en claro. Se ignora y se borra.
    if ("access_token" in parsed) persistAuth(perfil);
    return perfil;
  } catch {
    return vacio;
  }
}

function persistAuth(state: AuthState): void {
  if (state.rol === null) {
    sessionStorage.removeItem(STORAGE_KEY);
    return;
  }
  const { rol, carnet, nombre, id, cargo } = state;
  sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ rol, carnet, nombre, id, cargo }),
  );
}

export function getAuthState(): AuthState {
  return { ...authState };
}

export function setAuthState(state: AuthState): void {
  authState = { ...state };
  persistAuth(authState);
  notifyAuthChange();
}

export function clearAuthState(): void {
  authState = {
    access_token: null,
    rol: null,
    carnet: null,
    nombre: null,
    id: null,
  };
  persistAuth(authState);
  notifyAuthChange();
}

/**
 * Getter del access token actual.
 *
 * CRITICO (Fase 1, bug kick-al-login): `authState` es un binding `export let`
 * reasignable. Hacer `const { authState } = await import("./auth")` congela una
 * copia de la referencia vieja; tras un refresh del axios, los fetch nativos
 * (consultas/borradores) seguian enviando el token vencido -> 401 -> refresh
 * concurrente -> doble rotacion -> ReplayError -> logout. Usar SIEMPRE este
 * getter para leer el token actual en cada request.
 */
export function getAccessToken(): string | null {
  return authState.access_token;
}

// --- Sincronizacion con AuthContext ---
// El interceptor de axios reasigna authState en un refresh sin pasar por
// setAuthState; el AuthContext (estado React) quedaba desincronizado. Estos
// listeners permiten notificar cuando el token cambia por refresh.

type AuthChangeListener = () => void;
const authChangeListeners = new Set<AuthChangeListener>();

function notifyAuthChange(): void {
  for (const listener of authChangeListeners) listener();
}

export function onAuthChange(listener: AuthChangeListener): () => void {
  authChangeListeners.add(listener);
  return () => {
    authChangeListeners.delete(listener);
  };
}

// Cliente HTTP base. Proxy /api → http://localhost:8000 configurado en vite.config.ts.
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true, // envía cookies httpOnly automáticamente
});

/** Config de axios que reporta el % de subida (0-100) de un upload. */
export const conProgreso = (onProgreso?: (pct: number) => void) => ({
  onUploadProgress: (e: AxiosProgressEvent) => {
    if (onProgreso && e.total)
      onProgreso(Math.round((e.loaded * 100) / e.total));
  },
});

// Authorization header por request.
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (authState.access_token !== null) {
    config.headers.Authorization = `Bearer ${authState.access_token}`;
  }
  return config;
});

// Retry en 401 con un único intento de refresh (singleton compartido).
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    if (
      error.response?.status === 401 &&
      !original._retry &&
      reintentaEn401(original.url)
    ) {
      original._retry = true;
      const usado = String(original.headers.Authorization ?? "").replace(
        "Bearer ",
        "",
      );
      try {
        const newToken = await tokenParaReintento(usado || null);
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        clearAuthState();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  },
);

// --- Auth API ---

export interface LoginResponse {
  access_token: string;
  rol: string;
  carnet: string;
  nombre: string;
  id: number;
  cargo: string;
}

export interface Solicitar2FaResponse {
  requiere_2fa: boolean;
  carnet: string;
}

/** POST /auth/login — paso 1. Si el usuario tiene email_verificado,
 *  el backend responde {requiere_2fa: true} (sin tokens). */
export async function login(
  carnet: string,
  password: string,
): Promise<LoginResponse | Solicitar2FaResponse> {
  const { data } = await api.post<LoginResponse | Solicitar2FaResponse>(
    "/auth/login",
    { carnet, password },
  );
  return data;
}

/** POST /auth/verificar-2fa — paso 2. Valida el código y emite tokens. */
export async function verificar2Fa(
  carnet: string,
  codigo: string,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/verificar-2fa", {
    carnet,
    codigo,
  });
  setAuthState({
    access_token: data.access_token,
    rol: data.rol,
    carnet: data.carnet,
    nombre: data.nombre,
    id: data.id,
    cargo: data.cargo,
  });
  return data;
}

/** Redirige según rol. */
export function rutaSegunRol(rol: string): string {
  return rol === "administrador" ? "/admin" : "/asistente";
}

/**
 * Refresca el access token (cookie httpOnly -> nuevo par de tokens).
 *
 * Fase 1 (bug kick-al-login): SINGLETON idempotente. Cualquier llamador
 * (interceptor axios, fetchWithAuth de consultas/borradores) que dispare un
 * refresh mientras ya hay uno en vuelo REUTILIZA la misma promesa. Sin esto,
 * dos 401 concurrentes rotaban el MISMO refresh token dos veces -> el segundo
 * recibia ReplayError (token ya revocado) -> revocacion total -> logout.
 *
 * Actualiza `authState` y notifica a los listeners (AuthContext).
 */
let refreshPromise: Promise<string> | null = null;

async function rotarRefresh(): Promise<string> {
  const { data } = await api.post<{ access_token: string }>("/auth/refresh");
  authState = { ...authState, access_token: data.access_token };
  persistAuth(authState);
  notifyAuthChange();
  return data.access_token;
}

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise !== null) {
    return refreshPromise;
  }
  // El singleton es por pestaña; la cookie es compartida. Dos pestañas
  // refrescando a la vez mandan la MISMA cookie -> el backend lo ve como
  // replay (Regla 2) y revoca la sesión en todas. Web Locks serializa entre
  // pestañas: la segunda rota con la cookie ya renovada por la primera.
  refreshPromise =
    typeof navigator !== "undefined" && navigator.locks
      ? navigator.locks.request("auth-refresh", rotarRefresh)
      : rotarRefresh();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

/** Rutas donde un 401 es la respuesta final (credenciales), no un token vencido. */
const SIN_REFRESH = [
  "/auth/login",
  "/auth/refresh",
  "/auth/verificar-2fa",
  "/auth/logout",
];

export function reintentaEn401(url: string | undefined): boolean {
  return !SIN_REFRESH.some((ruta) => url?.includes(ruta));
}

/**
 * Token para reintentar una request que dio 401 habiendo enviado `tokenUsado`.
 * Si mientras tanto otro refresh ya lo rotó (401 tardío), se reusa el actual
 * sin volver a rotar el refresh token.
 */
export async function tokenParaReintento(
  tokenUsado: string | null,
): Promise<string> {
  const actual = authState.access_token;
  if (actual !== null && actual !== tokenUsado) return actual;
  return refreshAccessToken();
}

export async function logout(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } catch {
    // Red caída o 500 al revocar: la sesión local se cierra igual (el
    // refresh token expira solo); relanzar dejaba al usuario sin poder salir.
  } finally {
    clearAuthState();
  }
}

// --- Admin API ---

export interface UsuarioDTO {
  id: number;
  carnet: string;
  nombre: string;
  rol: string;
  cargo: string;
  activo: boolean;
  email?: string | null;
  email_verificado?: boolean;
}

export async function crearUsuario(
  body: CrearUsuarioBody,
): Promise<UsuarioDTO> {
  const { data } = await api.post<UsuarioDTO>("/admin/usuarios", body);
  return data;
}

export interface CrearUsuarioBody {
  carnet: string;
  nombre: string;
  password: string;
  rol: "administrador" | "supervisor" | "operador_juridico";
  cargo: string;
  email?: string | null;
}

export async function modificarUsuario(
  carnet: string,
  body: ModificarUsuarioBody,
): Promise<UsuarioDTO> {
  const { data } = await api.patch<UsuarioDTO>(
    `/admin/usuarios/${carnet}`,
    body,
  );
  return data;
}

export interface ModificarUsuarioBody {
  rol?: "administrador" | "supervisor" | "operador_juridico";
  cargo?: string;
  activo?: boolean;
  email?: string | null;
  nombre?: string;
  carnet?: string;
}

export async function desbloquear2Fa(carnet: string): Promise<void> {
  await api.post(`/admin/usuarios/${carnet}/desbloquear-2fa`);
}

export async function resetPassword(
  carnet: string,
  nuevaPassword: string,
): Promise<void> {
  await api.post(`/admin/usuarios/${carnet}/reset-password`, {
    nueva_password: nuevaPassword,
  });
}

// --- Perfil propio (GET/PATCH /auth/me) ---

export interface PerfilDTO {
  id: number;
  nombre: string;
  carnet: string;
  email: string | null;
  rol: string;
  cargo: string;
  created_at: string | null;
}

export async function obtenerPerfil(): Promise<PerfilDTO> {
  const { data } = await api.get<PerfilDTO>("/auth/me");
  return data;
}

export async function actualizarPerfil(body: {
  nombre: string;
  email?: string | null;
  password_actual?: string;
  password_nueva?: string;
}): Promise<PerfilDTO> {
  const { data } = await api.patch<PerfilDTO>("/auth/me", body);
  return data;
}
