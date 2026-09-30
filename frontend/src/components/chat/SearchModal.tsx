// Modal de busqueda: filtra conversaciones por titulo y por contenido de
// mensajes (via onBuscar, que usa chatStore.buscarConversaciones). Resultados
// agrupados por fecha (Hoy / Ayer / 7 dias / Mes / Meses anteriores / Anios).
// CRUD por resultado: abrir (click), renombrar inline y eliminar (soft).
//
// Impeccable a11y: Escape para cerrar, focus trap basico entre el input,
// el botón cerrar y los resultados visibles.

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X, Pencil, Trash2 } from "lucide-react";

import type { Conversacion, EspacioTrabajo } from "../../lib/chatTypes";
import {
  GROUP_LABELS,
  getMonthName,
  groupConversacionesPorFecha,
} from "../../utils/chatGrouping";

import styles from "./SearchModal.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  conversaciones: Conversacion[];
  espacios: EspacioTrabajo[];
  onSelect: (id: string) => void;
  onBuscar: (query: string) => Conversacion[];
  onRenombrar: (id: string, titulo: string) => void;
  onEliminar: (id: string) => void;
}

export function SearchModal({
  open,
  onClose,
  conversaciones,
  espacios,
  onSelect,
  onBuscar,
  onRenombrar,
  onEliminar,
}: Props) {
  const [query, setQuery] = useState("");
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [editandoTitulo, setEditandoTitulo] = useState("");
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setEditandoId(null);
      setEditandoTitulo("");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'input, button, [href], [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const carpetaDe = useMemo(() => {
    const map = new Map<string, string>();
    for (const esp of espacios) {
      for (const c of conversaciones) {
        if (c.espacio_trabajo_id === esp.id) {
          map.set(c.id, esp.nombre);
        }
      }
    }
    return map;
  }, [conversaciones, espacios]);

  // Busqueda por titulo Y contenido de mensajes (el store filtra ambos).
  const filtrados = useMemo(() => {
    const q = query.trim();
    if (!q) return [];
    return onBuscar(q);
  }, [query, onBuscar]);

  const grupos = useMemo(
    () => groupConversacionesPorFecha(filtrados),
    [filtrados],
  );

  if (!open) return null;

  function handleSelect(id: string) {
    onSelect(id);
    onClose();
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") onClose();
  }

  function iniciarRename(c: Conversacion) {
    setEditandoId(c.id);
    setEditandoTitulo(c.titulo);
  }

  function guardarRename() {
    if (editandoId !== null) {
      const nuevo = editandoTitulo.trim();
      if (nuevo) onRenombrar(editandoId, nuevo);
    }
    setEditandoId(null);
    setEditandoTitulo("");
  }

  function renderResult(c: Conversacion) {
    const editando = editandoId === c.id;
    return (
      <div key={c.id} className={styles.resultRow}>
        {editando ? (
          <input
            autoFocus
            className={styles.resultRow__input}
            value={editandoTitulo}
            onChange={(e) => setEditandoTitulo(e.target.value)}
            onBlur={guardarRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") guardarRename();
              if (e.key === "Escape") {
                setEditandoId(null);
                setEditandoTitulo("");
              }
            }}
            aria-label="Nombre de la conversacion"
          />
        ) : (
          <button
            type="button"
            className={styles.result}
            onClick={() => handleSelect(c.id)}
            title={c.titulo}
          >
            <span className={styles.result__title}>{c.titulo}</span>
            {carpetaDe.get(c.id) && (
              <span className={styles.result__folder}>
                {carpetaDe.get(c.id)}
              </span>
            )}
          </button>
        )}
        {!editando && (
          <div className={styles.resultRow__actions}>
            <button
              type="button"
              className={styles.resultRow__btn}
              aria-label={`Renombrar ${c.titulo}`}
              title="Renombrar"
              onClick={() => iniciarRename(c)}
            >
              <Pencil size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.resultRow__btn}
              aria-label={`Eliminar ${c.titulo}`}
              title="Eliminar (soft)"
              onClick={() => onEliminar(c.id)}
            >
              <Trash2 size={14} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Buscar conversaciones"
      onKeyDown={handleKey}
    >
      <div
        ref={dialogRef}
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKey}
      >
        <div className={styles.header}>
          <Search size={16} aria-hidden="true" />
          <input
            className={styles.input}
            autoFocus
            placeholder="Buscar conversaciones..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Buscar"
          />
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </div>

        <div className={styles.list}>
          {query.trim() === "" ? (
            <div className={styles.empty}>
              Escribe para buscar por titulo o por contenido de mensajes.
            </div>
          ) : filtrados.length === 0 ? (
            <div className={styles.empty}>Sin resultados.</div>
          ) : (
            <>
              {(["hoy", "ayer", "ultimos7dias", "esteMes"] as const).map(
                (k) =>
                  grupos[k].length > 0 && (
                    <div key={k}>
                      <div className={styles.section}>{GROUP_LABELS[k]}</div>
                      {grupos[k].map(renderResult)}
                    </div>
                  ),
              )}
              {Object.entries(grupos.meses)
                .sort(([a], [b]) => b.localeCompare(a))
                .map(
                  ([monthKey, list]) =>
                    list.length > 0 && (
                      <div key={monthKey}>
                        <div className={styles.section}>
                          {getMonthName(
                            Number(monthKey.split("-")[1]),
                            Number(monthKey.split("-")[0]),
                          )}
                        </div>
                        {list.map(renderResult)}
                      </div>
                    ),
                )}
              {Object.entries(grupos.anios)
                .sort(([a], [b]) => Number(b) - Number(a))
                .map(
                  ([yearKey, list]) =>
                    list.length > 0 && (
                      <div key={yearKey}>
                        <div className={styles.section}>{yearKey}</div>
                        {list.map(renderResult)}
                      </div>
                    ),
                )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
