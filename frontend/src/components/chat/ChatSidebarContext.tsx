// SidebarProvider: visibilidad del panel de historial del chat en
// /asistente/consultar. Es el ÚNICO toggle lateral de la app (el rail de
// navegación general es fijo). Escritorio: se recuerda la preferencia.
// Móvil (≤768px): es un drawer y siempre arranca cerrado.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface SidebarContextValue {
  historialAbierto: boolean;
  toggleHistorial: () => void;
  cerrarHistorial: () => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

const STORAGE_KEY = "asistente:historial-abierto";
const MOVIL = "(max-width: 768px)";

function esMovil(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.(MOVIL).matches;
}

function readInitial(): boolean {
  if (esMovil()) return false;
  try {
    return localStorage.getItem(STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [historialAbierto, setAbierto] = useState<boolean>(readInitial);

  useEffect(() => {
    if (esMovil()) return; // el drawer móvil no altera la preferencia de escritorio
    try {
      localStorage.setItem(STORAGE_KEY, historialAbierto ? "1" : "0");
    } catch {
      // storage bloqueado: la preferencia solo vive en memoria
    }
  }, [historialAbierto]);

  const toggleHistorial = useCallback(() => setAbierto((v) => !v), []);
  const cerrarHistorial = useCallback(() => setAbierto(false), []);

  const value = useMemo(
    () => ({ historialAbierto, toggleHistorial, cerrarHistorial }),
    [historialAbierto, toggleHistorial, cerrarHistorial],
  );

  return (
    <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
  );
}

export function useSidebar() {
  const ctx = useContext(SidebarContext);
  if (!ctx) {
    throw new Error("useSidebar debe usarse dentro de SidebarProvider");
  }
  return ctx;
}
