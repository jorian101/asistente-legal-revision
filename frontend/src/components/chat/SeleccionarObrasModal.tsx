// SeleccionarObrasModal: selector de obras del expediente para la consulta.
//
// Sin selección previa, todas las obras vienen marcadas; con selección previa
// (obra_ids de la conversación) se respeta. Buscador, agrupado por tipo de
// documento y contador "N de M". Cada fila muestra archivo y autor (instancia
// inferior o usuario·cargo). Al confirmar, guarda la selección (obra_ids).
//
// La doctrina (privada/recomendada/global) vive en el SelectorFuentes, no acá.

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";

import {
  type ObraResumenDTO,
  listarHistorialExpediente,
} from "../../api/expedientes";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { Button, Modal, StateMessage } from "../ui";

import styles from "./SeleccionarObrasModal.module.css";

function autorDe(obra: ObraResumenDTO): string {
  if (obra.autor_instancia) return obra.autor_instancia;
  if (obra.autor_nombre) {
    return obra.autor_cargo
      ? `${obra.autor_nombre} · ${obra.autor_cargo}`
      : obra.autor_nombre;
  }
  return "—";
}

interface Props {
  expedienteId: number;
  /** Selección previa (null = todas por defecto). */
  inicial: number[] | null;
  onConfirmar: (obraIds: number[] | null) => void;
  onCerrar: () => void;
}

export function SeleccionarObrasModal({
  expedienteId,
  inicial,
  onConfirmar,
  onCerrar,
}: Props) {
  const [obras, setObras] = useState<ObraResumenDTO[] | null>(null);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState("");
  // La selección previa solo siembra el estado al cargar; no se re-aplica en
  // cada render (el array del store cambia de identidad al recargar).
  const inicialRef = useRef(inicial);

  useEffect(() => {
    let cancelado = false;
    listarHistorialExpediente(expedienteId, { solo_propias: false })
      .then((resp) => {
        if (cancelado) return;
        setObras(resp.obras);
        const previa = inicialRef.current;
        const ids = resp.obras.map((o) => o.id);
        setSeleccion(
          new Set(
            previa === null ? ids : ids.filter((id) => previa.includes(id)),
          ),
        );
      })
      .catch((err) => {
        if (!cancelado)
          toast(
            mensajeError(err, "No se pudieron cargar los obrados"),
            "error",
          );
      });
    return () => {
      cancelado = true;
    };
  }, [expedienteId]);

  const grupos = useMemo(() => {
    const q = query.trim().toLowerCase();
    const porTipo = new Map<string, ObraResumenDTO[]>();
    for (const o of obras ?? []) {
      if (q && !`${o.nombre_archivo} ${autorDe(o)}`.toLowerCase().includes(q))
        continue;
      porTipo.set(o.tipo_documento, [
        ...(porTipo.get(o.tipo_documento) ?? []),
        o,
      ]);
    }
    return [...porTipo.entries()];
  }, [obras, query]);

  function toggle(obraId: number) {
    setSeleccion((prev) => {
      const next = new Set(prev);
      if (next.has(obraId)) next.delete(obraId);
      else next.add(obraId);
      return next;
    });
  }

  function confirmar() {
    // null = todas (por defecto); si el usuario desmarcó alguna, pasar la lista.
    const todas = obras !== null && seleccion.size === obras.length;
    onConfirmar(todas ? null : Array.from(seleccion));
  }

  const total = obras?.length ?? 0;
  const todasMarcadas = total > 0 && seleccion.size === total;

  // "Seleccionar todas" queda indeterminado con una selección parcial.
  const todasRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (todasRef.current)
      todasRef.current.indeterminate = seleccion.size > 0 && !todasMarcadas;
  }, [seleccion, todasMarcadas]);

  return (
    <Modal
      open
      title="Obrados del expediente"
      subtitle={
        obras === null
          ? "Cargando…"
          : `${seleccion.size} de ${total} seleccionado${total === 1 ? "" : "s"} para la consulta`
      }
      onClose={onCerrar}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={seleccion.size === 0}>
            Aplicar selección
          </Button>
        </>
      }
    >
      <div className={styles.toolbar}>
        <label className={styles.buscar}>
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            className="input"
            placeholder="Buscar por archivo o autor…"
            aria-label="Buscar obrados"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className={styles.item}>
          <input
            ref={todasRef}
            type="checkbox"
            checked={todasMarcadas}
            disabled={total === 0}
            onChange={() =>
              setSeleccion(
                todasMarcadas ? new Set() : new Set(obras?.map((o) => o.id)),
              )
            }
          />
          Seleccionar todas
        </label>
      </div>

      {obras === null && (
        <StateMessage tipo="cargando">Cargando obrados…</StateMessage>
      )}
      {obras !== null && total === 0 && (
        <StateMessage tipo="vacio">
          Este expediente no tiene obrados.
        </StateMessage>
      )}
      {obras !== null && total > 0 && grupos.length === 0 && (
        <StateMessage tipo="vacio">
          Ningún obrado coincide con «{query.trim()}».
        </StateMessage>
      )}
      {grupos.map(([tipo, items]) => (
        <section key={tipo} className={styles.grupo}>
          <h3 className={styles.grupoTitulo}>
            {tipo.charAt(0).toUpperCase() + tipo.slice(1).replaceAll("_", " ")}
            <span className={styles.grupoCuenta}>{items.length}</span>
          </h3>
          {items.map((o) => (
            <label key={o.id} className={styles.item}>
              <input
                type="checkbox"
                checked={seleccion.has(o.id)}
                onChange={() => toggle(o.id)}
              />
              <span className={styles.itemBody}>
                <span className={styles.itemNombre}>{o.nombre_archivo}</span>
                <span className={styles.itemMeta}>{autorDe(o)}</span>
              </span>
            </label>
          ))}
        </section>
      ))}
    </Modal>
  );
}
