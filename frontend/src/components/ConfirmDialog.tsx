// ConfirmDialog: confirmación de acciones destructivas o que requieren doble
// intención (ej. reconciliar Qdrant). Es un `Modal size="sm"`: hereda
// Escape/backdrop (salvo busy), focus trap y retorno del foco. El foco
// inicial va a Cancelar para que un Enter accidental no confirme.

import { type ReactNode } from "react";

import { Button } from "./ui/Button";
import Modal from "./ui/Modal";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  busy = false,
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      busy={busy}
      size="sm"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onCancel}
            disabled={busy}
            data-autofocus
          >
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Procesando..." : confirmLabel}
          </Button>
        </>
      }
    >
      {message}
    </Modal>
  );
}
