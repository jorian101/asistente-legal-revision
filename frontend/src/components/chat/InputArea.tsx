// InputArea: compositor del chat. Textarea auto-alto a lo ancho y, debajo, la
// barra de adjuntos (expediente, jurisprudencia, doctrina, normas) + enviar /
// cancelar: el textarea no compite por ancho con los botones (en 320px quedaba
// sin espacio). Con teclado físico Enter envía y Shift+Enter salta de línea; en
// táctil Enter es salto de línea (no hay Shift) y se envía con el botón.

import {
  useLayoutEffect,
  useRef,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  ArrowUp,
  BookMarked,
  FolderOpen,
  Landmark,
  Scale,
  Square,
} from "lucide-react";

import styles from "./InputArea.module.css";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
  onAdjuntarExpediente: () => void;
  onAdjuntarNormas: () => void;
  onAdjuntarDoctrina: () => void;
  onAdjuntarJurisprudencia: () => void;
  cargando: boolean;
  deshabilitado?: boolean;
}

const MIN_ALTURA = 24;

/** Tope de alto: 200px, o 30% del alto visible (con el teclado abierto). */
const maxAltura = () => Math.min(200, window.innerHeight * 0.3);

const esTactil = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(pointer: coarse)").matches === true;

export function InputArea({
  value,
  onChange,
  onSend,
  onCancel,
  onAdjuntarExpediente,
  onAdjuntarNormas,
  onAdjuntarDoctrina,
  onAdjuntarJurisprudencia,
  cargando,
  deshabilitado = false,
}: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  // Layout effect: se mide antes de pintar (sin parpadeo de alto).
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ajustar = () => {
      const max = maxAltura();
      el.style.height = "auto";
      el.style.height = `${Math.max(MIN_ALTURA, Math.min(el.scrollHeight, max))}px`;
      el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
    };
    ajustar();
    window.addEventListener("resize", ajustar);
    return () => window.removeEventListener("resize", ajustar);
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing: Enter que confirma un acento/autocorrección no envía.
    if (e.nativeEvent.isComposing || esTactil()) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!cargando && !deshabilitado && value.trim().length > 0) {
        onSend();
      }
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (cargando || deshabilitado || value.trim().length === 0) return;
    onSend();
  }

  const vacio = value.trim().length === 0;

  return (
    <form className={styles.area} onSubmit={handleSubmit}>
      <div className={styles.field}>
        <textarea
          ref={ref}
          className={styles.textarea}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Escribe tu consulta jurídica…"
          aria-label="Consulta"
          rows={1}
          disabled={deshabilitado}
        />
        <div className={styles.barra}>
          <button
            type="button"
            className={styles.attach}
            onClick={onAdjuntarExpediente}
            disabled={deshabilitado}
            aria-label="Adjuntar expediente a la consulta"
            title="Adjuntar expediente a la consulta"
          >
            <FolderOpen size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={styles.attach}
            onClick={onAdjuntarJurisprudencia}
            disabled={deshabilitado}
            aria-label="Agregar jurisprudencia a la consulta"
            title="Agregar jurisprudencia a la consulta"
          >
            <Scale size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={styles.attach}
            onClick={onAdjuntarDoctrina}
            disabled={deshabilitado}
            aria-label="Agregar doctrina a la consulta"
            title="Agregar doctrina a la consulta"
          >
            <BookMarked size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={styles.attach}
            onClick={onAdjuntarNormas}
            disabled={deshabilitado}
            aria-label="Fijar normas en la consulta"
            title="Fijar normas en la consulta"
          >
            <Landmark size={18} aria-hidden="true" />
          </button>
          <span className={styles.hint}>
            Enter envía · Shift+Enter, nueva línea
          </span>
          {cargando ? (
            <button
              type="button"
              className={styles.cancel}
              onClick={onCancel}
              aria-label="Cancelar consulta"
            >
              <Square size={16} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="submit"
              className={styles.send}
              disabled={deshabilitado || vacio}
              aria-label="Enviar consulta"
            >
              <ArrowUp size={18} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
