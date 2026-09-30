// TopBar: cabecera única de /asistente/* y /admin/* (escritorio y móvil).
// Izquierda: ☰ (solo móvil) + ubicación "Área / Módulo". Derecha: búsqueda
// global (Ctrl/Cmd+K) y menú de usuario con nombre, cargo y rol.
// El título grande de cada página sigue en su PageHeader (h1).

import { useEffect, useRef, useState, type Ref } from "react";
import { Link } from "react-router-dom";
import { LogOut, Menu, Search, User } from "lucide-react";

import { Badge, type BadgeTone } from "./Badge";
import styles from "./TopBar.module.css";

interface TopBarProps {
  area: string;
  raiz: string;
  /** Módulo actual; null en el Inicio del área. */
  actual: string | null;
  nombre: string;
  /** Línea secundaria del menú: el cargo ("Vocal Relator"). */
  detalleUsuario: string;
  /** Badge siempre visible (también en móvil) con el rol del usuario. */
  rol: { label: string; tone: BadgeTone } | null;
  perfilTo: string;
  menuAbierto: boolean;
  onAbrirMenu: () => void;
  onBuscar: () => void;
  onLogout: () => void;
  menuBtnRef: Ref<HTMLButtonElement>;
}

function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean);
  return (partes[0]?.[0] ?? "?") + (partes[1]?.[0] ?? "");
}

export function TopBar({
  area,
  raiz,
  actual,
  nombre,
  detalleUsuario,
  rol,
  perfilTo,
  menuAbierto,
  onAbrirMenu,
  onBuscar,
  onLogout,
  menuBtnRef,
}: TopBarProps) {
  const [usuarioAbierto, setUsuarioAbierto] = useState(false);
  const usuarioRef = useRef<HTMLDivElement>(null);
  const esMac =
    typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onBuscar();
      }
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [onBuscar]);

  useEffect(() => {
    if (!usuarioAbierto) return;
    const cerrarFuera = (e: PointerEvent) => {
      if (!usuarioRef.current?.contains(e.target as Node)) {
        setUsuarioAbierto(false);
      }
    };
    const cerrarEscape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setUsuarioAbierto(false);
      usuarioRef.current?.querySelector("button")?.focus();
    };
    document.addEventListener("pointerdown", cerrarFuera);
    document.addEventListener("keydown", cerrarEscape);
    return () => {
      document.removeEventListener("pointerdown", cerrarFuera);
      document.removeEventListener("keydown", cerrarEscape);
    };
  }, [usuarioAbierto]);

  return (
    <header className={styles.barra}>
      <button
        ref={menuBtnRef}
        type="button"
        className={`${styles.iconBtn} ${styles.menuBtn}`}
        aria-label="Abrir menú de navegación"
        aria-expanded={menuAbierto}
        aria-controls="nav-rail"
        onClick={onAbrirMenu}
      >
        <Menu size={20} aria-hidden="true" />
      </button>

      <nav className={styles.ubicacion} aria-label="Ubicación">
        {actual === null ? (
          <span className={styles.actual} aria-current="page">
            {area}
          </span>
        ) : (
          <>
            <Link to={raiz} className={styles.area}>
              {area}
            </Link>
            <span className={styles.sep} aria-hidden="true">
              /
            </span>
            <span className={styles.actual} aria-current="page">
              {actual}
            </span>
          </>
        )}
      </nav>

      <button
        type="button"
        className={styles.buscar}
        onClick={onBuscar}
        aria-keyshortcuts="Control+K Meta+K"
      >
        <Search size={16} aria-hidden="true" />
        <span className={styles.buscarTexto}>Buscar…</span>
        <kbd className={styles.atajo}>{esMac ? "⌘K" : "Ctrl K"}</kbd>
      </button>

      {rol && (
        <span className={styles.rol} title={`Rol: ${rol.label}`}>
          <Badge tone={rol.tone}>{rol.label}</Badge>
        </span>
      )}
      <div className={styles.usuario} ref={usuarioRef}>
        <button
          type="button"
          className={styles.avatarBtn}
          aria-haspopup="menu"
          aria-expanded={usuarioAbierto}
          aria-label={`Cuenta de ${nombre}`}
          onClick={() => setUsuarioAbierto((v) => !v)}
        >
          <span className={styles.avatar} aria-hidden="true">
            {iniciales(nombre).toUpperCase()}
          </span>
          <span className={styles.usuarioTexto}>
            <span className={styles.usuarioNombre}>{nombre}</span>
            <span className={styles.usuarioDetalle}>{detalleUsuario}</span>
          </span>
        </button>
        {usuarioAbierto && (
          <div className={styles.menu} role="menu">
            <div className={styles.menuCabecera}>
              <strong>{nombre}</strong>
              <span>{detalleUsuario}</span>
            </div>
            <Link
              to={perfilTo}
              role="menuitem"
              className={styles.menuItem}
              onClick={() => setUsuarioAbierto(false)}
            >
              <User size={16} aria-hidden="true" />
              Mi perfil
            </Link>
            <button
              type="button"
              role="menuitem"
              className={styles.menuItem}
              onClick={() => {
                setUsuarioAbierto(false);
                onLogout();
              }}
            >
              <LogOut size={16} aria-hidden="true" />
              Cerrar sesión
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
