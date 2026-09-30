// RechazoModal: rechazo con motivo obligatorio, común a fuentes pendientes,
// recomendaciones y promociones de obrados. El motivo le llega a quien propuso.

import { useEffect, useState } from "react";

import { Button, Field, Modal } from "../ui";

interface Props {
  /** Nombre de lo que se rechaza; null = cerrado. */
  nombre: string | null;
  onCancelar: () => void;
  onConfirmar: (motivo: string) => void;
}

export function RechazoModal({ nombre, onCancelar, onConfirmar }: Props) {
  const [motivo, setMotivo] = useState("");

  useEffect(() => {
    if (nombre !== null) setMotivo("");
  }, [nombre]);

  return (
    <Modal
      open={nombre !== null}
      title="Rechazar"
      subtitle={nombre ?? undefined}
      onClose={onCancelar}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onCancelar}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            disabled={!motivo.trim()}
            onClick={() => onConfirmar(motivo.trim())}
          >
            Confirmar rechazo
          </Button>
        </>
      }
    >
      <Field
        id="motivo-rechazo"
        label="Motivo del rechazo"
        hint="Quien lo propuso verá este motivo."
      >
        <textarea
          id="motivo-rechazo"
          className="textarea"
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
        />
      </Field>
    </Modal>
  );
}
