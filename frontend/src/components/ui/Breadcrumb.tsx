// Breadcrumb: navegación padre → hijo dentro de una página (no reemplaza
// al sidebar). El último item es la ubicación actual (sin link).

import { Fragment } from "react";

import styles from "./Breadcrumb.module.css";

export interface BreadcrumbItem {
  label: string;
  /** Si se provee, el item es clicable (vuelve al padre). */
  onClick?: () => void;
}

interface Props {
  items: BreadcrumbItem[];
}

export default function Breadcrumb({ items }: Props) {
  return (
    <nav className={styles.breadcrumb} aria-label="Ruta de navegación">
      {items.map((item, idx) => {
        const esUltimo = idx === items.length - 1;
        return (
          <Fragment key={`${item.label}-${idx}`}>
            {idx > 0 && (
              <span className={styles.sep} aria-hidden="true">
                /
              </span>
            )}
            {item.onClick !== undefined && !esUltimo ? (
              <button
                type="button"
                className={styles.link}
                onClick={item.onClick}
              >
                {item.label}
              </button>
            ) : (
              <span
                className={esUltimo ? styles.actual : styles.texto}
                aria-current={esUltimo ? "page" : undefined}
              >
                {item.label}
              </span>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
