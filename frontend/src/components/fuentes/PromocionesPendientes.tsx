// Cola del supervisor: obrados propuestos para promoverse a jurisprudencia.
// Aprobar o rechazar con motivo obligatorio.

import { useEffect, useState } from "react";

import {
  listarPromocionesPendientes,
  resolverPromocion,
  type PromocionPendienteDTO,
} from "../../api/expedientes";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import styles from "./Fuentes.module.css";
import { Button, StateMessage } from "../ui";
import { RechazoModal } from "./RechazoModal";

export function PromocionesPendientes() {
  const [items, setItems] = useState<PromocionPendienteDTO[] | null>(null);
  const [rechazoDe, setRechazoDe] = useState<PromocionPendienteDTO | null>(
    null,
  );
  // Obrado con una resolución en curso: evita el doble envío.
  const [ocupadoId, setOcupadoId] = useState<number | null>(null);

  useEffect(() => {
    listarPromocionesPendientes()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  async function resolver(
    p: PromocionPendienteDTO,
    aprobar: boolean,
    motivo?: string,
  ) {
    setRechazoDe(null);
    if (p.expediente_id === null) return;
    setOcupadoId(p.obra_id);
    try {
      await resolverPromocion(
        p.expediente_id,
        p.obra_id,
        aprobar,
        aprobar ? undefined : motivo,
      );
      toast(
        aprobar ? "Obrado promovido a jurisprudencia." : "Propuesta rechazada.",
        "success",
      );
      setItems((prev) => (prev ?? []).filter((x) => x.obra_id !== p.obra_id));
    } catch (err) {
      toast(mensajeError(err, "No se pudo resolver la promoción."), "error");
    } finally {
      setOcupadoId(null);
    }
  }

  if (items === null) return <StateMessage tipo="cargando" />;
  if (items.length === 0)
    return (
      <StateMessage tipo="vacio">
        Sin obrados propuestos pendientes.
      </StateMessage>
    );

  return (
    <section aria-label="Obrados propuestos pendientes">
      <p className={styles.meta}>
        Obrados que un operador propuso como jurisprudencia. Si los aprobás,
        pasan a ser jurisprudencia del tribunal.
      </p>
      <ul className={styles.lista}>
        {items.map((p) => (
          <li key={p.obra_id} className={styles.item}>
            <div className={styles.info}>
              <strong>{p.nombre_archivo}</strong>
              <span className={styles.meta}>
                {p.tipo_documento}
                {p.expediente_id ? ` · Expediente Nº ${p.expediente_id}` : ""}
              </span>
            </div>
            <div className={styles.acciones}>
              <Button
                size="sm"
                disabled={ocupadoId !== null}
                loading={ocupadoId === p.obra_id}
                onClick={() => void resolver(p, true)}
              >
                Aprobar
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={ocupadoId !== null}
                onClick={() => setRechazoDe(p)}
              >
                Rechazar
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <RechazoModal
        nombre={rechazoDe?.nombre_archivo ?? null}
        onCancelar={() => setRechazoDe(null)}
        onConfirmar={(motivo) =>
          rechazoDe && void resolver(rechazoDe, false, motivo)
        }
      />
    </section>
  );
}
