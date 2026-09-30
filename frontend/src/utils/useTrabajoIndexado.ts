// Hook utilitario: seguir un trabajo de indexado (POST .../normas o /fuentes
// responde 202 con un job_id) hasta que termina, con cancelacion.
//
// Comparte el polling entre SubirFuenteForm (fuentes) y el formulario
// "Indexar norma" del admin (Corpus). Lo que cada formulario hace al
// terminar (toast, reset de campos, callback) queda en el propio formulario:
// el hook solo sigue el trabajo y expone `enCurso`/`cancelando`.

import { useEffect, useRef, useState } from "react";

import {
  cancelarTrabajo,
  obtenerTrabajo,
  type EstadoTrabajo,
  type Trabajo,
} from "../api/jobs";

/** Cada cuanto se consulta el estado de un indexado en curso. */
const INTERVALO_MS = 1500;

export function useTrabajoIndexado() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [estado, setEstado] = useState<EstadoTrabajo | null>(null);
  const [cancelando, setCancelando] = useState(false);
  // Corta el polling si el formulario se desmonta con el indexado en curso.
  const vivo = useRef(true);

  useEffect(
    () => () => {
      vivo.current = false;
    },
    [],
  );

  const enCurso = jobId !== null && estado === "en_curso";

  /**
   * Sigue un trabajo recien encolado hasta que termina (completado, cancelado
   * o error), o hasta que el componente se desmonta (devuelve `null`).
   */
  async function seguir(
    id: string,
    estadoInicial: EstadoTrabajo,
  ): Promise<Trabajo | null> {
    setJobId(id);
    setEstado(estadoInicial);
    while (vivo.current) {
      const trabajo = await obtenerTrabajo(id);
      if (trabajo.estado !== "en_curso") {
        if (vivo.current) {
          setJobId(null);
          setEstado(null);
        }
        return trabajo;
      }
      await new Promise((listo) => setTimeout(listo, INTERVALO_MS));
    }
    return null;
  }

  /** Pide cancelar el trabajo en curso. Relanza el error para que el llamador lo muestre. */
  async function cancelar(): Promise<void> {
    if (!jobId) return;
    setCancelando(true);
    try {
      await cancelarTrabajo(jobId);
    } catch (err) {
      setCancelando(false);
      throw err;
    }
  }

  return { enCurso, cancelando, seguir, cancelar };
}
