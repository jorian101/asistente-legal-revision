// Tooltip: componente de tooltip unificado, accesible y reutilizable.
// Basado en lucide-react + CSS nativo, sin dependencias externas.

import { useRef, useState } from "react";
import { type ReactNode } from "react";

import styles from "./Tooltip.module.css";

interface Props {
  children: ReactNode;
  content: ReactNode;
  position?: "top" | "bottom" | "left" | "right";
  delay?: number;
}

export function Tooltip({
  children,
  content,
  position = "top",
  delay = 200,
}: Props) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function show() {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(true), delay);
  }

  function hide() {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(false), delay);
  }

  return (
    <div
      className={styles.wrapper}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span className={styles.trigger}>{children}</span>
      {visible && (
        <div
          className={`${styles.tooltip} ${styles[position]}`}
          role="tooltip"
          data-position={position}
        >
          <div className={styles.content}>{content}</div>
          <div className={`${styles.arrow} ${styles[`arrow-${position}`]}`} />
        </div>
      )}
    </div>
  );
}
