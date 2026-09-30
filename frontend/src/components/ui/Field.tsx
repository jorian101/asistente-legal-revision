// Field: etiqueta + control + ayuda/error con el mismo ritmo en todos los
// formularios. El control lleva las clases globales `.input`/`.select`/
// `.textarea` (index.css) y el `id` que recibe Field.

import { type ReactNode } from "react";

import styles from "./Field.module.css";

interface FieldProps {
  id: string;
  label: ReactNode;
  children: ReactNode;
  /** Texto de ayuda bajo el control (id: `${id}-hint`). */
  hint?: ReactNode;
  /** Error de validación (id: `${id}-error`, role=alert). */
  error?: ReactNode;
  className?: string;
}

export function Field({
  id,
  label,
  children,
  hint,
  error,
  className = "",
}: FieldProps) {
  return (
    <div className={`${styles.field} ${className}`}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
