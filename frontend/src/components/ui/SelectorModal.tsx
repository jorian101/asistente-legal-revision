// SelectorModal: reemplazo de <select> para catálogos que crecen (usuarios,
// normas, expedientes). Modal con buscador, filtro segmentado opcional y
// filas densas con divisores; cada fila es el botón de elegir.
// El llamador mapea su dominio a Opcion y recibe el id elegido.

import { useEffect, useState, type ReactNode } from "react";
import { Search } from "lucide-react";

import Modal from "./Modal";
import { StateMessage } from "./StateMessage";
import styles from "./SelectorModal.module.css";

export interface OpcionSelector {
  id: string;
  titulo: string;
  detalle?: string;
  extra?: ReactNode;
  /** Valor del segmento al que pertenece (si hay `segmentos`). */
  segmento?: string;
}

interface Props {
  open: boolean;
  title: string;
  subtitle?: ReactNode;
  /** null = cargando. */
  opciones: OpcionSelector[] | null;
  /** [valor, texto]; se antepone «Todos». */
  segmentos?: [string, string][];
  placeholder: string;
  /** Aviso bajo el buscador (ej. lista truncada). */
  aviso?: ReactNode;
  /** Mensaje si no hay ninguna opción (antes de filtrar). */
  vacio?: ReactNode;
  seleccionado?: string;
  onSeleccionar: (id: string) => void;
  onClose: () => void;
}

const normalizar = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

export function SelectorModal({
  open,
  title,
  subtitle,
  opciones,
  segmentos,
  placeholder,
  aviso,
  vacio = "Sin resultados.",
  seleccionado,
  onSeleccionar,
  onClose,
}: Props) {
  const [query, setQuery] = useState("");
  const [segmento, setSegmento] = useState("");

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSegmento("");
  }, [open]);

  const q = normalizar(query.trim());
  const visibles = (opciones ?? []).filter(
    (o) =>
      (!segmento || o.segmento === segmento) &&
      (!q || normalizar(`${o.titulo} ${o.detalle ?? ""}`).includes(q)),
  );

  return (
    <Modal open={open} title={title} subtitle={subtitle} onClose={onClose}>
      <div className={styles.barra}>
        <label className={styles.buscar}>
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            className="input"
            placeholder={placeholder}
            aria-label={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {segmentos && (
          <div
            className={styles.segmentado}
            role="radiogroup"
            aria-label="Filtrar"
          >
            {[["", "Todos"] as [string, string], ...segmentos].map(
              ([valor, texto]) => (
                <button
                  key={valor}
                  type="button"
                  role="radio"
                  aria-checked={segmento === valor}
                  className={styles.segmento}
                  onClick={() => setSegmento(valor)}
                >
                  {texto}
                </button>
              ),
            )}
          </div>
        )}
      </div>
      {aviso && <p className={styles.aviso}>{aviso}</p>}
      {opciones === null ? (
        <StateMessage tipo="cargando" />
      ) : opciones.length === 0 ? (
        <StateMessage tipo="vacio">{vacio}</StateMessage>
      ) : visibles.length === 0 ? (
        <StateMessage tipo="vacio">Sin resultados.</StateMessage>
      ) : (
        <ul className={styles.lista} aria-label={title}>
          {visibles.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                className={styles.item}
                aria-current={o.id === seleccionado || undefined}
                onClick={() => onSeleccionar(o.id)}
              >
                <span className={styles.itemTexto}>
                  <span className={styles.titulo}>{o.titulo}</span>
                  {o.detalle && (
                    <span className={styles.detalle}>{o.detalle}</span>
                  )}
                </span>
                {o.extra}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
