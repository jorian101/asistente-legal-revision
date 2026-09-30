// ChatItem: item de conversacion en el sidebar.
// Misma composicion que la referencia: click selecciona, menu contextual
// (renombrar / fijar o desfijar / archivar / eliminar) y edicion inline del
// titulo con Enter para confirmar.

import { useEffect, useRef, useState } from "react";
import {
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Archive,
  Trash2,
} from "lucide-react";

import type { Conversacion } from "../../lib/chatTypes";

import styles from "./ChatItem.module.css";

interface Props {
  conversacion: Conversacion;
  selected: boolean;
  isPinned: boolean;
  /** F1: true mientras este chat genera una respuesta (aunque no sea el
   *  chat que se está mirando) — muestra un indicador junto al título. */
  generando?: boolean;
  onSelect: () => void;
  onRename: (nuevoTitulo: string) => void;
  onPin: () => void;
  onUnpin: () => void;
  onArchive: () => void;
  onDelete: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
}

export function ChatItem({
  conversacion,
  selected,
  isPinned,
  generando = false,
  onSelect,
  onRename,
  onPin,
  onUnpin,
  onArchive,
  onDelete,
  draggable = false,
  onDragStart,
}: Props) {
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [editando, setEditando] = useState(false);
  const [tituloEdit, setTituloEdit] = useState(conversacion.titulo);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number }>({
    top: 0,
    left: 0,
  });
  const itemRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuAbierto) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current && menuRef.current.contains(target)) return;
      if (itemRef.current && itemRef.current.contains(target)) return;
      setMenuAbierto(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuAbierto(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuAbierto]);

  useEffect(() => {
    if (editando && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editando]);

  function abrirMenu(e: React.MouseEvent) {
    e.stopPropagation();
    const btn = e.currentTarget as HTMLElement;
    const rect = btn.getBoundingClientRect();
    setMenuPos({ top: rect.bottom + 4, left: rect.right + 4 });
    setMenuAbierto((v) => !v);
  }

  function guardarEdicion() {
    const nuevo = tituloEdit.trim();
    if (nuevo && nuevo !== conversacion.titulo) onRename(nuevo);
    setEditando(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      guardarEdicion();
    } else if (e.key === "Escape") {
      setEditando(false);
      setTituloEdit(conversacion.titulo);
    }
  }

  function handleDragStart(e: React.DragEvent) {
    if (editando) {
      e.preventDefault();
      return;
    }
    onDragStart?.(e);
  }

  const clases = [
    styles.item,
    selected ? styles["item--active"] : "",
    isPinned ? styles["item--pinned"] : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <button
        ref={itemRef}
        type="button"
        className={clases}
        draggable={draggable && !editando}
        onDragStart={handleDragStart}
        onClick={() => {
          if (!editando) {
            setMenuAbierto(false);
            onSelect();
          }
        }}
        onDoubleClick={(e) => {
          e.stopPropagation();
          setEditando(true);
        }}
      >
        {isPinned && (
          <span className={styles.item__icon} aria-label="Fijado">
            <Pin size={12} />
          </span>
        )}
        {editando ? (
          <input
            ref={inputRef}
            className={styles.editing}
            value={tituloEdit}
            onChange={(e) => setTituloEdit(e.target.value)}
            onBlur={guardarEdicion}
            onKeyDown={handleKeyDown}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className={styles.item__title}>{conversacion.titulo}</span>
        )}
        {generando && (
          <span
            className={styles.item__generando}
            role="status"
            aria-label="Generando respuesta"
            title="Generando respuesta…"
          />
        )}
        <span
          className={styles.item__menu}
          onClick={abrirMenu}
          role="button"
          tabIndex={0}
          aria-label="Opciones"
          aria-expanded={menuAbierto}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              abrirMenu(e as unknown as React.MouseEvent);
            }
          }}
        >
          <MoreHorizontal size={14} />
        </span>
      </button>

      {menuAbierto && (
        <div
          ref={menuRef}
          className={styles.menu}
          style={{ top: menuPos.top, left: menuPos.left }}
          role="menu"
        >
          <button
            type="button"
            className={styles.menu__item}
            onClick={() => {
              setMenuAbierto(false);
              setEditando(true);
            }}
          >
            <span className={styles.menu__icon}>
              <Pencil size={14} />
            </span>
            Renombrar
          </button>
          {isPinned ? (
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => {
                setMenuAbierto(false);
                onUnpin();
              }}
            >
              <span className={styles.menu__icon}>
                <PinOff size={14} />
              </span>
              Desfijar
            </button>
          ) : (
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => {
                setMenuAbierto(false);
                onPin();
              }}
            >
              <span className={styles.menu__icon}>
                <Pin size={14} />
              </span>
              Fijar
            </button>
          )}
          <button
            type="button"
            className={styles.menu__item}
            onClick={() => {
              setMenuAbierto(false);
              onArchive();
            }}
          >
            <span className={styles.menu__icon}>
              <Archive size={14} />
            </span>
            Archivar
          </button>
          <button
            type="button"
            className={`${styles.menu__item} ${styles["menu__item--danger"]}`}
            onClick={() => {
              setMenuAbierto(false);
              onDelete();
            }}
          >
            <span className={styles.menu__icon}>
              <Trash2 size={14} />
            </span>
            Eliminar
          </button>
        </div>
      )}
    </>
  );
}
