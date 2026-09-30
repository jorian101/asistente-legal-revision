// SelectOtro: select de catálogo con opción "Otro" que abre un input libre.
//
// Regla anti-alucinación del vault: si el valor no está en el catálogo se
// conserva tal cual (texto libre), nunca se fuerza a un valor catalogado.
// - value en catálogo → select lo muestra seleccionado.
// - value NO en catálogo (legacy) → select en "Otro" + input con el valor.
// - elegir "Otro" → se limpia el input para escribir un valor nuevo.
//
// Modo Operate (impeccable): label visible, accesible, sin magia.

import { useEffect, useRef, useState } from "react";

import { type CatOption } from "../../config/catalogos";

import styles from "./SelectOtro.module.css";

export const VALOR_OTRO = "__otro__";

interface Props {
  id: string;
  label: string;
  opciones: readonly CatOption[];
  value: string;
  onChange: (valor: string) => void;
  required?: boolean;
  placeholder?: string;
  /** Label a mostrar para la opción "Otro". */
  otroLabel?: string;
  /** Clase CSS extra (heredar estilos de input del formulario contenedor). */
  className?: string;
}

export function SelectOtro({
  id,
  label,
  opciones,
  value,
  onChange,
  required = false,
  placeholder = "Escribir otro valor...",
  otroLabel = "Otro",
  className = "",
}: Props) {
  const valorLegacy = value !== "" && !opciones.some((o) => o.valor === value);
  const [modoOtro, setModoOtro] = useState(valorLegacy);
  const [otroTexto, setOtroTexto] = useState(valorLegacy ? value : "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Sincronizar cuando el value cambia externamente (edición de legacy).
  useEffect(() => {
    if (value !== "" && !opciones.some((o) => o.valor === value)) {
      setModoOtro(true);
      setOtroTexto(value);
    } else if (value === "") {
      // Si el padre limpió el value (ej. al elegir Otro), mantener modoOtro
      // para que el input quede listo para escribir.
      setModoOtro((m) => m);
    } else {
      setModoOtro(false);
    }
  }, [value, opciones]);

  function handleSelect(nuevo: string) {
    if (nuevo === VALOR_OTRO) {
      setModoOtro(true);
      setOtroTexto("");
      onChange("");
      requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }
    setModoOtro(false);
    onChange(nuevo);
  }

  return (
    <span className={`${styles.selectOtro} ${className}`}>
      <label className={styles.label} htmlFor={id}>
        {label} {required && <span aria-hidden="true">*</span>}
      </label>
      <select
        id={id}
        className={styles.select}
        value={modoOtro ? VALOR_OTRO : value}
        onChange={(e) => handleSelect(e.target.value)}
        required={required && !modoOtro}
      >
        <option value="" disabled>
          Seleccionar...
        </option>
        {opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.label}
          </option>
        ))}
        <option value={VALOR_OTRO}>{otroLabel}</option>
      </select>
      {modoOtro && (
        <input
          ref={inputRef}
          type="text"
          value={otroTexto}
          onChange={(e) => {
            setOtroTexto(e.target.value);
            onChange(e.target.value);
          }}
          placeholder={placeholder}
          required={required}
          aria-label={`${label} (otro valor)`}
        />
      )}
    </span>
  );
}
