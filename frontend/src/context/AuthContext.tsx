// AuthProvider: expone el context definido en useAuth.ts.
// Archivo de componentes solo, para satisfacer oxlint fast-refresh.

import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  clearAuthState,
  getAuthState,
  login as apiLogin,
  logout as apiLogout,
  onAuthChange,
  refreshAccessToken,
  setAuthState,
  verificar2Fa,
  type AuthState,
  type LoginResponse,
  type Solicitar2FaResponse,
} from "../api/auth";

import { AuthContext, type AuthContextValue } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(getAuthState());
  // Tras un F5 hay perfil en sessionStorage pero el access token (solo en memoria) se
  // perdio: se restaura con /auth/refresh antes de decidir si redirigir a /login.
  const [cargando, setCargando] = useState<boolean>(
    () => auth.rol !== null && auth.access_token === null,
  );

  useEffect(() => {
    if (!cargando) return;
    let activo = true;
    // refreshAccessToken es singleton: StrictMode (doble efecto) no duplica el POST ni
    // rota dos veces el refresh token (bug "kick-al-login").
    refreshAccessToken()
      .catch(() => clearAuthState())
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [cargando]);

  // Fase 1 (bug kick-al-login): sincronizar el estado React con el modulo
  // auth.ts cuando el interceptor hace un refresh (que reasigna authState sin
  // pasar por setAuthState). Sin esto, ProtectedRoute/isAuthenticated usaban
  // un token viejo y el guard podia expulsar tras un refresh.
  useEffect(() => {
    return onAuthChange(() => {
      setAuth(getAuthState());
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      isAuthenticated: auth.access_token !== null,
      cargando,
      async login(
        carnet: string,
        password: string,
      ): Promise<LoginResponse | Solicitar2FaResponse> {
        const resp = await apiLogin(carnet, password);
        // Si NO trae access_token, es el paso 2FA (aún no hay tokens).
        if (!("access_token" in resp)) {
          return resp;
        }
        const nuevo: AuthState = {
          access_token: resp.access_token,
          rol: resp.rol,
          carnet: resp.carnet,
          nombre: resp.nombre,
          id: resp.id,
          cargo: resp.cargo,
        };
        setAuthState(nuevo);
        setAuth(nuevo);
        return resp;
      },
      async completar2fa(
        carnet: string,
        codigo: string,
      ): Promise<LoginResponse> {
        const resp = await verificar2Fa(carnet, codigo);
        setAuth({
          access_token: resp.access_token,
          rol: resp.rol,
          carnet: resp.carnet,
          nombre: resp.nombre,
          id: resp.id,
          cargo: resp.cargo,
        });
        return resp;
      },
      async logout(): Promise<void> {
        await apiLogout();
        clearAuthState();
        setAuth({
          access_token: null,
          rol: null,
          carnet: null,
          nombre: null,
          id: null,
        });
      },
    }),
    [auth, cargando],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
