// EstadoSwitch: switch de estado binario (ej. activo ↔ archivado).
// Patrón extraído de Expedientes para reuso en módulos con soft delete.

import styles from "./EstadoSwitch.module.css";

interface Props {
  activo: boolean;
  disabled?: boolean;
  /** Etiquetas del estado, en orden [activo, inactivo]. */
  etiquetas?: [string, string];
  ariaLabel?: string;
  onChange: () => void;
}

export default function EstadoSwitch({
  activo,
  disabled = false,
  etiquetas = ["Activo", "Inactivo"],
  ariaLabel,
  onChange,
}: Props) {
  return (
    <label
      className={styles.switch}
      aria-label={
        ariaLabel ?? `Cambiar estado a ${activo ? etiquetas[1] : etiquetas[0]}`
      }
    >
      <input
        type="checkbox"
        className={styles.input}
        checked={activo}
        disabled={disabled}
        onChange={onChange}
      />
      <span className={styles.slider} />
      <span className={styles.label}>
        {activo ? etiquetas[0] : etiquetas[1]}
      </span>
    </label>
  );
}
