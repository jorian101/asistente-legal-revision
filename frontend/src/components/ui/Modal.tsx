// Modal: diálogo único de la app. Anatomía fija: cabecera (título + ×),
// cuerpo con scroll propio y pie opcional con las acciones.
// a11y: role=dialog + aria-modal + aria-labelledby, Escape y backdrop cierran
// (salvo `busy`), Tab queda atrapado dentro, el foco entra al abrir
// (`[data-autofocus]` > primer campo > primer botón) y vuelve al disparador.

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

import styles from "./Modal.module.css";

export type ModalSize = "sm" | "md" | "lg" | "xl";

export interface ModalProps {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  busy?: boolean;
  /** sm 440 · md 560 · lg 800 · xl 1100 (px). */
  size?: ModalSize;
  /** Texto corto bajo el título (contador, contexto). */
  subtitle?: ReactNode;
}

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  busy = false,
  size = "md",
  subtitle,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const inicial =
      dialog?.querySelector<HTMLElement>("[data-autofocus]") ??
      dialog?.querySelector<HTMLElement>(
        `.${styles.body} :is(input, select, textarea):not([disabled])`,
      ) ??
      dialog?.querySelector<HTMLElement>(
        `.${styles.body} button, .${styles.footer} button`,
      ) ??
      dialog?.querySelector<HTMLElement>("button");
    inicial?.focus();
    return () => prev?.focus?.();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      // Con diálogos apilados (ConfirmDialog sobre un Modal) solo reacciona
      // el de arriba: si no, un Escape cerraba los dos.
      const abiertos = document.querySelectorAll('[aria-modal="true"]');
      if (abiertos[abiertos.length - 1] !== dialogRef.current) return;
      if (e.key === "Escape") {
        if (busy) return;
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusables =
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLES);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  return (
    <div className={styles.backdrop} onClick={busy ? undefined : onClose}>
      <div
        ref={dialogRef}
        className={`${styles.dialog} ${styles[size]}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <div className={styles.headerTexto}>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            disabled={busy}
            aria-label="Cerrar"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer !== undefined && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}
