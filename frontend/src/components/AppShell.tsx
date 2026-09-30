// AppShell: estructura común de /asistente/* y /admin/*: NavRail a la
// izquierda (expandido o colapsado en escritorio, drawer en móvil) + TopBar +
// contenido. El drawer móvil se abre con ☰ (backdrop, Escape, cierre al navegar).

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import type { Modulo } from "../config/modulosPorRol";
import { labelRol } from "../config/modulosPorRol";
import { useAuth } from "../context/useAuth";
import { usePermisos } from "../context/usePermisos";
import { BusquedaGlobal } from "./BusquedaGlobal";
import { Footer } from "./Footer";
import { NavRail } from "./ui/NavRail";
import { StateMessage } from "./ui/StateMessage";
import type { BadgeTone } from "./ui/Badge";
import { TopBar } from "./ui/TopBar";

import styles from "./AppShell.module.css";

interface AppShellProps {
  modulos: Modulo[];
  raiz: string;
  /** Sin padding en el contenido (pantalla de chat a sangre). */
  sinPadding?: boolean;
}

const CLAVE_COLAPSADO = "shell:rail-colapsado";

// Tono del badge de rol: supervisor y operador se distinguen de un vistazo.
const TONO_ROL: Record<string, BadgeTone> = {
  administrador: "warning",
  supervisor: "info",
  operador_juridico: "neutral",
};

function leerColapsado(): boolean {
  try {
    return localStorage.getItem(CLAVE_COLAPSADO) === "1";
  } catch {
    return false;
  }
}

export function AppShell({ modulos, raiz, sinPadding = false }: AppShellProps) {
  const { auth, logout } = useAuth();
  const { puede } = usePermisos();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [colapsado, setColapsado] = useState(leerColapsado);
  const [buscando, setBuscando] = useState(false);
  const menuBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => setMenuAbierto(false), [location.pathname]);

  useEffect(() => {
    if (!menuAbierto) return;
    // Al abrir, el foco entra al drawer; Escape lo cierra y devuelve el foco a ☰.
    document.querySelector<HTMLElement>("#nav-rail nav a")?.focus();
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setMenuAbierto(false);
      menuBtnRef.current?.focus();
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [menuAbierto]);

  function toggleColapsado() {
    setColapsado((v) => {
      try {
        localStorage.setItem(CLAVE_COLAPSADO, v ? "0" : "1");
      } catch {
        // Sin storage: la preferencia dura lo que la pestaña.
      }
      return !v;
    });
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const abrirBusqueda = useCallback(() => setBuscando(true), []);

  const esAsistente = raiz === "/asistente";
  const perfilTo = `${raiz}/perfil`;
  const actual =
    location.pathname === raiz
      ? null
      : location.pathname === perfilTo
        ? "Mi perfil"
        : (modulos.find((m) => location.pathname.startsWith(m.to))?.label ??
          null);
  const nombre = auth.nombre ?? auth.carnet ?? "";
  const detalleUsuario = auth.cargo ?? "";
  const rol =
    auth.rol === null
      ? null
      : { label: labelRol(auth.rol), tone: TONO_ROL[auth.rol] ?? "neutral" };
  const esChat = location.pathname === "/asistente/consultar";

  return (
    <div className={styles.shell}>
      <NavRail
        modulos={modulos}
        raiz={raiz}
        perfilTo={perfilTo}
        abierto={menuAbierto}
        colapsado={colapsado}
        onToggleColapsado={toggleColapsado}
        onNavegar={() => setMenuAbierto(false)}
        onLogout={handleLogout}
      />
      {menuAbierto && (
        <button
          type="button"
          className={styles.backdrop}
          aria-label="Cerrar menú"
          onClick={() => setMenuAbierto(false)}
        />
      )}
      <div className={styles.main}>
        <TopBar
          area={esAsistente ? "Asistente jurídico" : "Administración"}
          raiz={raiz}
          actual={actual}
          nombre={nombre}
          detalleUsuario={detalleUsuario}
          rol={rol}
          perfilTo={perfilTo}
          menuAbierto={menuAbierto}
          onAbrirMenu={() => setMenuAbierto(true)}
          onBuscar={abrirBusqueda}
          onLogout={handleLogout}
          menuBtnRef={menuBtnRef}
        />
        <main
          className={`${styles.contenido}${sinPadding ? ` ${styles.sinPadding}` : ""}`}
        >
          {/* Las páginas cargan bajo demanda: el shell queda visible mientras. */}
          <Suspense fallback={<StateMessage tipo="cargando" />}>
            {sinPadding ? (
              <Outlet />
            ) : (
              <div className={styles.pagina}>
                <Outlet />
              </div>
            )}
          </Suspense>
        </main>
        {!esChat && <Footer />}
      </div>
      <BusquedaGlobal
        open={buscando}
        onClose={() => setBuscando(false)}
        paginas={modulos}
        usuarioId={esAsistente ? auth.id : null}
        conFuentes={esAsistente && puede("doctrina", "leer")}
      />
    </div>
  );
}
