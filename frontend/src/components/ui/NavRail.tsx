// NavRail: navegación general de /asistente/* y /admin/*.
// Escritorio: expandido (icono + etiqueta en fila) o colapsado a solo iconos,
// con un tooltip fijo por fuera del rail (el rail scrollea y recortaría uno
// absoluto). Móvil (≤768px): drawer expandido que abre el ☰ del TopBar; ahí
// Perfil y Salir siguen al pie porque el TopBar móvil es mínimo.

import { useState, type FocusEvent, type MouseEvent } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  Home,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  User,
} from "lucide-react";

import type { Modulo } from "../../config/modulosPorRol";
import { NOMBRE_SISTEMA } from "../../config/sistema";
import { SistemaLogo } from "./SistemaLogo";

import styles from "./NavRail.module.css";

interface NavRailProps {
  modulos: Modulo[];
  raiz: string;
  perfilTo: string;
  abierto: boolean;
  colapsado: boolean;
  onToggleColapsado: () => void;
  onNavegar: () => void;
  onLogout: () => void;
}

interface Tip {
  texto: string;
  top: number;
}

const claseLink = ({ isActive }: { isActive: boolean }) =>
  `${styles.link}${isActive ? ` ${styles.linkActivo}` : ""}`;

export function NavRail({
  modulos,
  raiz,
  perfilTo,
  abierto,
  colapsado,
  onToggleColapsado,
  onNavegar,
  onLogout,
}: NavRailProps) {
  const [tip, setTip] = useState<Tip | null>(null);

  // Solo en colapsado: las etiquetas visibles hacen redundante el tooltip.
  function mostrarTip(e: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) {
    if (!colapsado) return;
    const r = e.currentTarget.getBoundingClientRect();
    const texto = e.currentTarget.getAttribute("aria-label") ?? "";
    setTip({ texto, top: r.top + r.height / 2 });
  }
  const eventosTip = {
    onMouseEnter: mostrarTip,
    onFocus: mostrarTip,
    onMouseLeave: () => setTip(null),
    onBlur: () => setTip(null),
  };

  const items = [
    { to: raiz, label: "Inicio", descripcion: "", icono: Home, end: true },
    ...modulos.map((m) => ({ ...m, end: false })),
  ];

  return (
    <aside
      id="nav-rail"
      className={[
        styles.rail,
        abierto && styles.abierto,
        colapsado && styles.colapsado,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Link
        to={raiz}
        className={styles.brand}
        onClick={onNavegar}
        aria-label={`${NOMBRE_SISTEMA} · Inicio`}
      >
        <SistemaLogo className={styles.logo} />
        <span className={styles.brandNombre}>{NOMBRE_SISTEMA}</span>
      </Link>
      <nav className={styles.nav} aria-label="Navegación principal">
        {items.map((m) => {
          const Icono = m.icono;
          return (
            <NavLink
              key={m.to}
              to={m.to}
              end={m.end}
              className={claseLink}
              onClick={() => {
                setTip(null);
                onNavegar();
              }}
              aria-label={m.label}
              title={colapsado || !m.descripcion ? undefined : m.descripcion}
              {...eventosTip}
            >
              {Icono && <Icono size={20} aria-hidden="true" />}
              <span className={styles.label}>{m.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className={styles.pie}>
        <Link
          to={perfilTo}
          className={`${styles.link} ${styles.soloMovil}`}
          onClick={onNavegar}
        >
          <User size={20} aria-hidden="true" />
          <span className={styles.label}>Perfil</span>
        </Link>
        <button
          type="button"
          className={`${styles.link} ${styles.soloMovil}`}
          onClick={onLogout}
        >
          <LogOut size={20} aria-hidden="true" />
          <span className={styles.label}>Salir</span>
        </button>
        <button
          type="button"
          className={`${styles.link} ${styles.soloEscritorio}`}
          onClick={() => {
            setTip(null);
            onToggleColapsado();
          }}
          aria-label={colapsado ? "Expandir menú" : "Colapsar menú"}
          aria-expanded={!colapsado}
          aria-controls="nav-rail"
          {...eventosTip}
        >
          {colapsado ? (
            <PanelLeftOpen size={20} aria-hidden="true" />
          ) : (
            <PanelLeftClose size={20} aria-hidden="true" />
          )}
          <span className={styles.label}>Colapsar</span>
        </button>
      </div>
      {tip && (
        <span
          className={styles.tip}
          style={{ top: tip.top }}
          role="tooltip"
          aria-hidden="true"
        >
          {tip.texto}
        </span>
      )}
    </aside>
  );
}
