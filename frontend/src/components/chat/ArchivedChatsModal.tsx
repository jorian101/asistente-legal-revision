// Modal de chats archivados: lista, desarchivar, eliminar individual, limpiar
// todos. Usa ConfirmDialog para las acciones destructivas.

import { useState } from "react";
import { ArchiveRestore, Trash2 } from "lucide-react";

import ConfirmDialog from "../ConfirmDialog";
import { Button, Modal, StateMessage } from "../ui";
import type { Conversacion } from "../../lib/chatTypes";

import styles from "./ArchivedChatsModal.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  conversaciones: Conversacion[];
  onDesarchivar: (id: string) => void;
  onEliminar: (id: string) => void;
  onSeleccionar: (id: string) => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-BO", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function ArchivedChatsModal({
  open,
  onClose,
  conversaciones,
  onDesarchivar,
  onEliminar,
  onSeleccionar,
}: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmLimpiar, setConfirmLimpiar] = useState(false);
  const [procesando, setProcesando] = useState(false);

  async function confirmarEliminar() {
    if (!confirmDeleteId) return;
    setProcesando(true);
    try {
      onEliminar(confirmDeleteId);
    } finally {
      setProcesando(false);
      setConfirmDeleteId(null);
    }
  }

  async function confirmarLimpiar() {
    setProcesando(true);
    try {
      for (const c of conversaciones) onEliminar(c.id);
    } finally {
      setProcesando(false);
      setConfirmLimpiar(false);
    }
  }

  return (
    <>
      <Modal
        open={open}
        title="Chats archivados"
        subtitle={
          conversaciones.length > 0
            ? `${conversaciones.length} conversación${conversaciones.length === 1 ? "" : "es"}`
            : undefined
        }
        onClose={onClose}
        busy={procesando}
        size="md"
        footer={
          <>
            {conversaciones.length > 0 && (
              <Button
                variant="ghost"
                className={styles.limpiar}
                onClick={() => setConfirmLimpiar(true)}
                disabled={procesando}
              >
                <Trash2 size={16} aria-hidden="true" />
                Eliminar todos
              </Button>
            )}
            <Button variant="secondary" onClick={onClose}>
              Cerrar
            </Button>
          </>
        }
      >
        {conversaciones.length === 0 ? (
          <StateMessage tipo="vacio">No hay chats archivados.</StateMessage>
        ) : (
          <ul className={styles.list}>
            {conversaciones.map((c) => (
              <li key={c.id} className={styles.row}>
                <button
                  type="button"
                  className={styles.row__title}
                  onClick={() => onSeleccionar(c.id)}
                >
                  {c.titulo}
                  <span className={styles.row__date}>
                    {formatDate(c.created_at)}
                  </span>
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  iconOnly
                  onClick={() => onDesarchivar(c.id)}
                  disabled={procesando}
                  aria-label={`Desarchivar ${c.titulo}`}
                  title="Desarchivar"
                >
                  <ArchiveRestore aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  iconOnly
                  className={styles.eliminar}
                  onClick={() => setConfirmDeleteId(c.id)}
                  disabled={procesando}
                  aria-label={`Eliminar ${c.titulo}`}
                  title="Eliminar"
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Eliminar chat archivado"
        message="Esta accion eliminara el chat y todos sus mensajes. No se puede deshacer."
        confirmLabel="Eliminar"
        cancelLabel="Cancelar"
        danger
        busy={procesando}
        onConfirm={confirmarEliminar}
        onCancel={() => setConfirmDeleteId(null)}
      />

      <ConfirmDialog
        open={confirmLimpiar}
        title="Eliminar todos los chats archivados"
        message="Esta accion eliminara todos los chats archivados y sus mensajes. No se puede deshacer."
        confirmLabel="Eliminar todo"
        cancelLabel="Cancelar"
        danger
        busy={procesando}
        onConfirm={confirmarLimpiar}
        onCancel={() => setConfirmLimpiar(false)}
      />
    </>
  );
}
