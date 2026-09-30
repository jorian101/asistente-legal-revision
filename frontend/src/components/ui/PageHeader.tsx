// PageHeader: cabecera de página consistente (título + subtítulo + acciones opcionales).

import { type ReactNode } from "react";

import styles from "./PageHeader.module.css";

interface Props {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  subtitle,
  actions,
  className = "",
}: Props) {
  return (
    <header className={`${styles.header} ${className}`}>
      <div className={styles.text}>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}
