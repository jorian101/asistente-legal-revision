// Cola del supervisor: recomendaciones de fuentes a expedientes pendientes de aprobación.

import { useEffect, useState } from "react";

import {
  aprobarRecomendacion,
  aprobarTodasRecomendaciones,
  listarRecomendacionesPendientes,
  rechazarRecomendacion,
  type RecomendacionDTO,
} from "../../api/doctrina";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import styles from "./Fuentes.module.css";
import ConfirmDialog from "../ConfirmDialog";
import { Button, StateMessage } from "../ui";
import { RechazoModal } from "./RechazoModal";

export function RecomendacionesPendientes() {
  const [items, setItems] = useState<RecomendacionDTO[] | null>(null);
  const [rechazoDe, setRechazoDe] = useState<RecomendacionDTO | null>(null);
  // Acción en curso: id de la fila o "todo"; evita el doble envío.
  const [ocupado, setOcupado] = useState<number | "todo" | null>(null);
  const [confirmarTodo, setConfirmarTodo] = useState(false);

  useEffect(() => {
    listarRecomendacionesPendientes()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  const quitar = (id: number) =>
    setItems((prev) => (prev ?? []).filter((r) => r.id !== id));

  async function aprobar(id: number) {
    setOcupado(id);
    try {
      await aprobarRecomendacion(id);
      toast("Fuente sugerida aprobada.", "success");
      quitar(id);
    } catch (err) {
      toast(mensajeError(err, "No se pudo aprobar."), "error");
    } finally {
      setOcupado(null);
    }
  }

  async function rechazar(id: number, motivo: string) {
    setRechazoDe(null);
    setOcupado(id);
    try {
      await rechazarRecomendacion(id, motivo);
      toast("Fuente sugerida rechazada.", "success");
      quitar(id);
    } catch (err) {
      toast(mensajeError(err, "No se pudo rechazar."), "error");
    } finally {
      setOcupado(null);
    }
  }

  async function aprobarTodo() {
    setOcupado("todo");
    try {
      const res = await aprobarTodasRecomendaciones();
      toast(`${res.aprobadas} fuente(s) sugerida(s) aprobada(s).`, "success");
      setItems([]);
    } catch (err) {
      toast(mensajeError(err, "No se pudo aprobar todo."), "error");
    } finally {
      setOcupado(null);
      setConfirmarTodo(false);
    }
  }

  if (items === null) return <StateMessage tipo="cargando" />;
  if (items.length === 0)
    return (
      <StateMessage tipo="vacio">
        Sin fuentes sugeridas pendientes.
      </StateMessage>
    );

  return (
    <section aria-label="Fuentes sugeridas pendientes">
      <p className={styles.meta}>
        Fuentes que un usuario sugirió para un expediente. Al aprobarlas quedan
        vinculadas.
      </p>
      <div className={styles.barra}>
        <span className={styles.meta}>
          {items.length} pendiente{items.length === 1 ? "" : "s"}
        </span>
        <Button
          variant="secondary"
          disabled={ocupado !== null}
          onClick={() => setConfirmarTodo(true)}
        >
          Aprobar todo
        </Button>
      </div>
      <ul className={styles.lista}>
        {items.map((r) => (
          <li key={r.id} className={styles.item}>
            <div className={styles.info}>
              <strong>{r.nombre_archivo}</strong>
              <span className={styles.meta}>
                {r.recomendado_por_nombre
                  ? `Recomendado por ${r.recomendado_por_nombre}`
                  : "Recomendado"}
                {` · Expediente Nº ${r.expediente_id}`}
              </span>
            </div>
            <div className={styles.acciones}>
              <Button
                size="sm"
                disabled={ocupado !== null}
                loading={ocupado === r.id}
                onClick={() => void aprobar(r.id)}
              >
                Aprobar
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={ocupado !== null}
                onClick={() => setRechazoDe(r)}
              >
                Rechazar
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={confirmarTodo}
        title="Aprobar todas las fuentes sugeridas"
        message={`Se aprobarán las ${items.length} fuentes sugeridas pendientes y quedarán vinculadas a sus expedientes.`}
        confirmLabel="Aprobar todo"
        busy={ocupado === "todo"}
        onConfirm={() => void aprobarTodo()}
        onCancel={() => setConfirmarTodo(false)}
      />
      <RechazoModal
        nombre={rechazoDe?.nombre_archivo ?? null}
        onCancelar={() => setRechazoDe(null)}
        onConfirmar={(motivo) =>
          rechazoDe && void rechazar(rechazoDe.id, motivo)
        }
      />
    </section>
  );
}
