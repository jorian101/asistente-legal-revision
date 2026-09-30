// Button: botón reutilizable con variantes (primary, secondary, ghost, danger)
// y tamaños (md por defecto, sm para filas de tabla/lista y toolbars densas).
// Accesible: focus-visible, disabled, loading, aria.

import { type ButtonHTMLAttributes, forwardRef } from "react";

import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  loading?: boolean;
  iconOnly?: boolean;
  "aria-label"?: string;
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  (
    {
      children,
      variant = "primary",
      size = "md",
      loading = false,
      iconOnly = false,
      disabled,
      className = "",
      "aria-label": ariaLabel,
      ...rest
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        className={`${styles.btn} ${styles[variant]} ${size === "sm" ? styles.sm : ""} ${isDisabled ? styles.disabled : ""} ${iconOnly ? styles.iconOnly : ""} ${className}`}
        disabled={isDisabled}
        aria-disabled={isDisabled}
        aria-busy={loading}
        aria-label={ariaLabel}
        {...rest}
      >
        {loading ? (
          <span className={styles.spinner} aria-hidden="true" />
        ) : (
          children
        )}
      </button>
    );
  },
);

Button.displayName = "Button";
