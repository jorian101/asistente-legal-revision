// AccionesRapidas: botones de acceso directo para generar documentos legales
// desde el chat cuando hay un expediente adjunto (Fase 3D).
//
// Al hacer click pre-llenan la consulta (no envían directo) para que el
// usuario la ajuste antes de enviar — el backend clasifica el tipo y genera
// el borrador con la plantilla correspondiente.

import { FileText, ListChecks, Scale } from "lucide-react";

import styles from "./AccionesRapidas.module.css";

interface Props {
  onElegirConsulta: (texto: string, tipoForzado?: string) => void;
  deshabilitado?: boolean;
}

const ACCIONES: Array<{
  label: string;
  icon: React.ReactNode;
  texto: string;
  tipoForzado?: string;
}> = [
  {
    label: "Auto de vista",
    icon: <Scale size={14} aria-hidden="true" />,
    texto:
      "Elaborá el auto de vista del expediente, con la fundamentación y la resolución correspondiente.",
  },
  {
    label: "Dictamen de radicatoria",
    icon: <FileText size={14} aria-hidden="true" />,
    texto:
      "Elaborá el dictamen de radicatoria del expediente, determinando la competencia y radicatoria.",
  },
  {
    // HU-21 (patrón role-prompting del Vocal, criterio-vocal #7):
    // fundamentos de derecho aislados citando norma + precedente.
    label: "Sugerir argumentación",
    icon: <ListChecks size={14} aria-hidden="true" />,
    texto:
      "Compórtate como Auditor Militar experto en justicia penal militar y sugerí la argumentación para los Fundamentos de Derecho de este caso, citando los artículos y jurisprudencia aplicables.",
  },
  {
    label: "Dictamen de fondo",
    icon: <FileText size={14} aria-hidden="true" />,
    texto:
      "Elaborá el dictamen de fondo del expediente, analizando los hechos y el derecho aplicable.",
    tipoForzado: "dictamen_fondo",
  },
  {
    label: "Relación de obrados",
    icon: <ListChecks size={14} aria-hidden="true" />,
    texto:
      "Elaborá la relación de obrados del expediente, resumiendo los antecedentes foja por foja.",
    tipoForzado: "relacion_obrados",
  },
  {
    label: "Comparar jurisprudencia",
    icon: <Scale size={14} aria-hidden="true" />,
    texto:
      "Compará en una tabla la siguiente jurisprudencia aplicable, señalando coincidencias y diferencias: SCP_1 / SCP_2.",
  },
];

export function AccionesRapidas({
  onElegirConsulta,
  deshabilitado = false,
}: Props) {
  return (
    <div className={styles.wrapper}>
      <span className={styles.label}>Acciones rápidas:</span>
      <div className={styles.botones}>
        {ACCIONES.map((a) => (
          <button
            key={a.label}
            type="button"
            className={styles.btn}
            disabled={deshabilitado}
            onClick={() => onElegirConsulta(a.texto, a.tipoForzado)}
            title={`Generar: ${a.label}`}
          >
            {a.icon}
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}
