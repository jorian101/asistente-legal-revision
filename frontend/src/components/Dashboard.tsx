// Dashboard: pantalla de bienvenida post-login con los módulos del área
// como cards navegables (ícono + label + descripción + arrow), en el orden
// del catálogo de permisos del backend (/auth/permisos).
//
// Modo Operate (impeccable): cards escaneables, jerarquía clara, elevación
// Lifted al hover (DESIGN.md), accesibles (links reales).

import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../context/useAuth";
import { usePermisos } from "../context/usePermisos";
import { modulosDashboardArea, labelRol } from "../config/modulosPorRol";
import { NOMBRE_SISTEMA } from "../config/sistema";
import { PageHeader } from "./ui";

import styles from "./Dashboard.module.css";

interface Props {
  area: "admin" | "asistente";
  titulo: string;
}

export function Dashboard({ area, titulo }: Props) {
  const { auth } = useAuth();
  const { permisos } = usePermisos();
  const modulos = modulosDashboardArea(permisos, area);

  return (
    <div>
      <PageHeader
        title={`Hola, ${auth.nombre ?? auth.carnet}`}
        subtitle={`${labelRol(auth.rol)} · ${NOMBRE_SISTEMA} — ${titulo}`}
      />

      <section className={styles.grid} aria-label="Módulos disponibles">
        {modulos.map((m) => {
          const Icono = m.icono;
          return (
            <Link key={m.to} to={m.to} className={styles.card}>
              {Icono && (
                <Icono className={styles.cardIcono} aria-hidden="true" />
              )}
              <span className={styles.cardBody}>
                <span className={styles.cardLabel}>{m.label}</span>
                <span className={styles.cardDesc}>{m.descripcion}</span>
              </span>
              <ArrowRight className={styles.cardArrow} aria-hidden="true" />
            </Link>
          );
        })}
        {modulos.length === 0 && (
          <p className={styles.vacio}>No tenés módulos disponibles.</p>
        )}
      </section>
    </div>
  );
}
