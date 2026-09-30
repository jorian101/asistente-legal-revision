// Formulario común para subir una fuente (norma, jurisprudencia o libro).
// El operador la sube privada; el supervisor, directo a global.
//
// La indexacion es asincrona: la subida responde 202 con un job_id y desde aca
// se sigue el estado hasta que termina, con opcion de cancelar el indexado
// (useTrabajoIndexado, compartido con el formulario "Indexar norma" del admin).

import { useState, type FormEvent } from "react";

import {
  subirFuente,
  type CategoriaFuente,
  type JerarquiaNorma,
} from "../../api/fuentes";
import type { EstadoTrabajo, Trabajo } from "../../api/jobs";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { useTrabajoIndexado } from "../../utils/useTrabajoIndexado";

import { Button, Field } from "../ui";
import styles from "./Fuentes.module.css";

interface Props {
  categoria: CategoriaFuente;
  esSupervisor: boolean;
  /** Se llama con el trabajo ya terminado: ahi esta el resultado. */
  onSubida: (trabajo: Trabajo) => void;
}

export function SubirFuenteForm({ categoria, esSupervisor, onSubida }: Props) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [nombre, setNombre] = useState("");
  const [jerarquia, setJerarquia] = useState<JerarquiaNorma>("supletoria");
  const [tipo, setTipo] = useState<"scp_tcp" | "sentencia_cidh">("scp_tcp");
  const [subiendo, setSubiendo] = useState(false);
  const [progreso, setProgreso] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const trabajo = useTrabajoIndexado();

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!archivo || nombre.trim().length < 3) return;
    setSubiendo(true);
    setProgreso(0);
    setError(null);
    try {
      const encolado = await subirFuente(
        {
          archivo,
          categoria,
          nombre: nombre.trim(),
          jerarquia: categoria === "norma" ? jerarquia : undefined,
          tipo: categoria === "jurisprudencia" ? tipo : undefined,
        },
        setProgreso,
      );
      setSubiendo(false);

      const final = await trabajo.seguir(
        encolado.job_id,
        encolado.estado as EstadoTrabajo,
      );
      if (final === null) return; // desmontado mientras seguía el trabajo
      if (final.estado === "completado") {
        toast(
          esSupervisor
            ? "Fuente cargada como global."
            : "Fuente cargada como privada. Proponla para que el supervisor la apruebe.",
          "success",
        );
        setArchivo(null);
        setNombre("");
        onSubida(final);
      } else if (final.estado === "cancelado") {
        toast("Indexado cancelado.", "info");
      } else {
        const msg = final.error ?? "No se pudo indexar la fuente.";
        setError(msg);
        toast(msg, "error");
      }
    } catch (err) {
      const msg = mensajeError(err, "No se pudo subir la fuente.");
      setError(msg);
      toast(msg, "error");
    } finally {
      setSubiendo(false);
    }
  }

  async function cancelar() {
    try {
      await trabajo.cancelar();
      toast("Cancelando el indexado…", "info");
    } catch (err) {
      toast(mensajeError(err, "No se pudo cancelar el indexado."), "error");
    }
  }

  return (
    <form
      className={styles.form}
      onSubmit={enviar}
      aria-label={`Subir ${categoria}`}
    >
      <Field
        id={`fuente-archivo-${categoria}`}
        label="Archivo (.pdf, .docx, .txt)"
        error={error}
      >
        <input
          id={`fuente-archivo-${categoria}`}
          type="file"
          className="input"
          accept=".pdf,.docx,.txt"
          onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
        />
      </Field>
      <Field id={`fuente-nombre-${categoria}`} label="Nombre">
        <input
          id={`fuente-nombre-${categoria}`}
          className="input"
          value={nombre}
          minLength={3}
          maxLength={200}
          required
          onChange={(e) => setNombre(e.target.value)}
        />
      </Field>
      {categoria === "norma" && (
        <Field id="fuente-jerarquia" label="Jerarquía">
          <select
            id="fuente-jerarquia"
            className="select"
            value={jerarquia}
            onChange={(e) => setJerarquia(e.target.value as JerarquiaNorma)}
          >
            <option value="suprema">Suprema</option>
            <option value="militar">Militar</option>
            <option value="supletoria">Supletoria</option>
          </select>
        </Field>
      )}
      {categoria === "jurisprudencia" && (
        <Field id="fuente-origen" label="Origen">
          <select
            id="fuente-origen"
            className="select"
            value={tipo}
            onChange={(e) =>
              setTipo(e.target.value as "scp_tcp" | "sentencia_cidh")
            }
          >
            <option value="scp_tcp">Tribunal Constitucional (TCP)</option>
            <option value="sentencia_cidh">Corte Interamericana (CIDH)</option>
          </select>
        </Field>
      )}
      <div className={styles.formAcciones}>
        <span className={styles.meta}>
          {trabajo.enCurso
            ? "Indexando: podés cancelarlo, y se detiene al terminar la fase en curso."
            : esSupervisor
              ? "Visible para todos los usuarios."
              : "Solo la ves vos. Podés proponerla como global después."}
        </span>
        {trabajo.enCurso && (
          <Button
            type="button"
            variant="secondary"
            onClick={cancelar}
            disabled={trabajo.cancelando}
          >
            {trabajo.cancelando ? "Cancelando…" : "Cancelar indexado"}
          </Button>
        )}
        <Button
          type="submit"
          aria-busy={subiendo || trabajo.enCurso}
          disabled={
            subiendo || trabajo.enCurso || !archivo || nombre.trim().length < 3
          }
        >
          {subiendo
            ? progreso < 100
              ? `Subiendo ${progreso}%`
              : "Encolando…"
            : trabajo.enCurso
              ? "Indexando…"
              : esSupervisor
                ? "Subir como global"
                : "Subir como privada"}
        </Button>
      </div>
    </form>
  );
}
