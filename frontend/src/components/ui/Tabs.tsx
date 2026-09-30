// Tabs: pestañas únicas de la app (antes había tres implementaciones).
// Patrón WAI-ARIA: tablist + tab con aria-selected, flechas ←/→ mueven la
// selección y solo la pestaña activa está en el orden de tabulación.

import { useRef, type KeyboardEvent, type ReactNode } from "react";

import styles from "./Tabs.module.css";

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  /** Contador opcional (pendientes, resultados). */
  count?: number;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  className = "",
}: TabsProps<T>) {
  const ref = useRef<HTMLDivElement>(null);

  function alTeclear(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = items.findIndex((t) => t.value === value);
    const paso = e.key === "ArrowRight" ? 1 : -1;
    const siguiente = items[(i + paso + items.length) % items.length];
    onChange(siguiente.value);
    ref.current
      ?.querySelector<HTMLButtonElement>(`[data-value="${siguiente.value}"]`)
      ?.focus();
  }

  return (
    <div
      ref={ref}
      className={`${styles.tabs} ${className}`}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={alTeclear}
    >
      {items.map((t) => {
        const activa = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            data-value={t.value}
            aria-selected={activa}
            tabIndex={activa ? 0 : -1}
            className={styles.tab}
            onClick={() => onChange(t.value)}
          >
            {t.label}
            {t.count !== undefined && (
              <span className={styles.count}>{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
