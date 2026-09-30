// Badge: etiqueta de estado (indexado, pendiente, privada, error…).

import { type ReactNode } from "react";

import styles from "./Badge.module.css";

export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral";

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: BadgeTone;
  children: ReactNode;
}) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}
