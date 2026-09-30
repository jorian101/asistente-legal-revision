// useAuth.ts: define el Context + el hook.
// AuthContext.tsx solo exporta el Provider que consume este Context.

import { createContext, useContext } from "react";

import {
  type AuthState,
  type LoginResponse,
  type Solicitar2FaResponse,
} from "../api/auth";

export interface AuthContextValue {
  auth: AuthState;
  isAuthenticated: boolean;
  /** true mientras se restaura la sesion tras un F5 (perfil guardado, sin token aun). */
  cargando: boolean;
  login: (
    carnet: string,
    password: string,
  ) => Promise<LoginResponse | Solicitar2FaResponse>;
  completar2fa: (carnet: string, codigo: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth debe usarse dentro de AuthProvider");
  }
  return ctx;
}
