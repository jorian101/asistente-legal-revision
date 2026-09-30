// StateMessage: estado de carga / vacío / error unificado para listas y paneles.

import { type ReactNode } from "react";

import styles from "./StateMessage.module.css";

type Tipo = "cargando" | "vacio" | "error";

interface Props {
  tipo: Tipo;
  children?: ReactNode;
}

const TEXTO_POR_DEFECTO: Record<Tipo, string> = {
  cargando: "Cargando…",
  vacio: "Sin resultados.",
  error: "No se pudo cargar la información.",
};

export function StateMessage({ tipo, children }: Props) {
  return (
    <p
      className={`${styles.mensaje} ${styles[tipo]}`}
      role={tipo === "error" ? "alert" : "status"}
    >
      {children ?? TEXTO_POR_DEFECTO[tipo]}
    </p>
  );
}
