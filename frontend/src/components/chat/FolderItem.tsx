// FolderItem: carpeta del sidebar (Fijados / Archivados / personalizadas).
// Header expand/collapse, edicion inline del nombre y menu contextual
// (renombrar / eliminar) salvo en las carpetas de sistema (Fijados, Archivados).
// Drop zone: acepta chats arrastrados desde otros lugares del sidebar.

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Folder,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

import ConfirmDialog from "../ConfirmDialog";
import type { Conversacion, EspacioTrabajo } from "../../lib/chatTypes";

import { ChatItem } from "./ChatItem";

import styles from "./FolderItem.module.css";

interface Props {
  espacio: EspacioTrabajo;
  chats: Conversacion[];
  conversacionActivaId: string | null;
  /** Inicia en modo edicion del nombre (carpeta recien creada). */
  autoEdit?: boolean;
  /** F1: ids de chats con una generación en curso (indicador en el item). */
  chatsGenerando?: ReadonlySet<string>;
  onSelectChat: (id: string) => void;
  onRename: (id: string, nuevoNombre: string) => void;
  onDelete: (id: string) => void;
  onRenameChat: (id: string, nuevoTitulo: string) => void;
  onDeleteChat: (id: string) => void;
  onPinChat: (id: string) => void;
  onUnpinChat: (id: string) => void;
  onArchiveChat: (id: string) => void;
  onDropChat: (chatId: string, espacioId: string) => void;
}

export function FolderItem({
  espacio,
  chats,
  conversacionActivaId,
  autoEdit = false,
  chatsGenerando,
  onSelectChat,
  onRename,
  onDelete,
  onRenameChat,
  onDeleteChat,
  onPinChat,
  onUnpinChat,
  onArchiveChat,
  onDropChat,
}: Props) {
  const esSistema = espacio.tipo === "fijado" || espacio.tipo === "archivado";
  const [abierto, setAbierto] = useState(true);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [editando, setEditando] = useState(autoEdit);
  const [nombreEdit, setNombreEdit] = useState(espacio.nombre);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number }>({
    top: 0,
    left: 0,
  });
  const [dropping, setDropping] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editando && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editando]);

  useEffect(() => {
    if (!menuAbierto) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current && menuRef.current.contains(target)) return;
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

  function toggle(e: React.MouseEvent) {
    if (editando) return;
    e.stopPropagation();
    setAbierto((v) => !v);
  }

  function abrirMenu(e: React.MouseEvent) {
    e.stopPropagation();
    const btn = e.currentTarget as HTMLElement;
    const rect = btn.getBoundingClientRect();
    setMenuPos({ top: rect.bottom + 4, left: rect.right + 4 });
    setMenuAbierto((v) => !v);
  }

  function guardarEdicion() {
    const nuevo = nombreEdit.trim();
    if (nuevo && nuevo !== espacio.nombre) onRename(espacio.id, nuevo);
    setEditando(false);
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      guardarEdicion();
    } else if (e.key === "Escape") {
      setEditando(false);
      setNombreEdit(espacio.nombre);
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDropping(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDropping(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDropping(false);
    const raw = e.dataTransfer.getData("application/x-chat-id");
    if (raw) onDropChat(raw, espacio.id);
  }

  return (
    <>
      <div
        className={`${styles.folder} ${dropping ? styles.folder__dropping : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <button
          type="button"
          className={styles.folder__header}
          onClick={toggle}
          aria-expanded={abierto}
        >
          <span className={styles.folder__toggle} aria-hidden="true">
            {abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <Folder size={14} />
          {editando ? (
            <input
              ref={inputRef}
              className={styles.editing}
              value={nombreEdit}
              onChange={(e) => setNombreEdit(e.target.value)}
              onBlur={guardarEdicion}
              onKeyDown={handleKey}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className={styles.folder__name}>{espacio.nombre}</span>
          )}
          <span className={styles.folder__count}>{chats.length}</span>
          {!esSistema && (
            <span
              className={styles.folder__menu}
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
          )}
        </button>

        {menuAbierto && !esSistema && (
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
            <button
              type="button"
              className={`${styles.menu__item} ${styles["menu__item--danger"]}`}
              onClick={() => {
                setMenuAbierto(false);
                setConfirmDelete(true);
              }}
            >
              <span className={styles.menu__icon}>
                <Trash2 size={14} />
              </span>
              Eliminar
            </button>
          </div>
        )}

        {abierto && chats.length > 0 && (
          <div className={styles.folder__body}>
            {chats.map((c) => (
              <ChatItem
                key={c.id}
                conversacion={c}
                selected={conversacionActivaId === c.id}
                isPinned={espacio.tipo === "fijado"}
                generando={chatsGenerando?.has(c.id) ?? false}
                onSelect={() => onSelectChat(c.id)}
                onRename={(nuevo) => onRenameChat(c.id, nuevo)}
                onPin={() => onPinChat(c.id)}
                onUnpin={() => onUnpinChat(c.id)}
                onArchive={() => onArchiveChat(c.id)}
                onDelete={() => onDeleteChat(c.id)}
                draggable
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Eliminar carpeta"
        message={
          <>
            ¿Seguro que deseas eliminar la carpeta{" "}
            <strong>{espacio.nombre}</strong>?
            {chats.length > 0 && (
              <>
                {" "}
                Los {chats.length} chat(s) contenidos volveran al area principal
                del sidebar.
              </>
            )}
          </>
        }
        confirmLabel="Eliminar"
        cancelLabel="Cancelar"
        danger
        onConfirm={() => {
          setConfirmDelete(false);
          onDelete(espacio.id);
        }}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
