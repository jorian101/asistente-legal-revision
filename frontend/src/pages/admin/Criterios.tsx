// Admin Criterios: ver y editar los criterios del asistente (Plan A).
//
// Solo administrador (módulo 'criterios'). El contenido se sincroniza desde
// la carpeta de criterios del proyecto (seed_criterio_vault.py). El admin
// puede editar el texto del criterio y sus metadatos (procedencia, recomendada).
//
// Operate: estado local, sin Redux.

import { useEffect, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

import {
  actualizarCriterio,
  descargarObra,
  listarCriterios,
  type CriterioDTO,
} from "../../api/doctrina";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import ConfirmDialog from "../../components/ConfirmDialog";
import { Button, PageHeader, StateMessage } from "../../components/ui";

import "./Criterios.css";

/** Quita el frontmatter YAML (--- ... ---) si el contenido lo trae. */
function stripFrontmatter(texto: string): string {
  if (!texto.startsWith("---")) return texto;
  const fin = texto.indexOf("\n---", 3);
  if (fin === -1) return texto;
  return texto.slice(fin + 4).replace(/^\n+/, "");
}

function renderMarkdown(texto: string): string {
  const html = marked.parse(texto, { gfm: true, breaks: true });
  return DOMPurify.sanitize(html as string);
}

export default function CriteriosAdmin() {
  const [criterios, setCriterios] = useState<CriterioDTO[]>([]);
  const [cargando, setCargando] = useState(false);
  const [editando, setEditando] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [procedencia, setProcedencia] = useState("");
  const [recomendada, setRecomendada] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [confirmDescartar, setConfirmDescartar] = useState(false);

  function cargar() {
    setCargando(true);
    listarCriterios()
      .then(setCriterios)
      .catch((err) =>
        toast(
          mensajeError(err, "No se pudieron cargar los criterios"),
          "error",
        ),
      )
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function iniciarEdicion(c: CriterioDTO) {
    setEditando(c.id);
    setTexto(stripFrontmatter(c.contenido_texto));
    setProcedencia(c.procedencia ?? "");
    setRecomendada(c.recomendada);
  }

  // Cancelar con cambios sin guardar pide confirmación.
  function cancelar(c: CriterioDTO) {
    const cambiado =
      texto !== stripFrontmatter(c.contenido_texto) ||
      procedencia !== (c.procedencia ?? "") ||
      recomendada !== c.recomendada;
    if (cambiado) setConfirmDescartar(true);
    else setEditando(null);
  }

  async function guardar(id: number) {
    setGuardando(true);
    try {
      await actualizarCriterio(id, {
        contenido_texto: texto,
        procedencia: procedencia || undefined,
        recomendada,
      });
      toast("Criterio actualizado", "success");
      setEditando(null);
      cargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo guardar el criterio"), "error");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="criterios-admin">
      <PageHeader
        title="Criterios del asistente"
        subtitle="Ver y editar cómo se comporta Valnor en sus respuestas."
      />

      <p className="criterios-admin__hint">
        El contenido proviene de los criterios del proyecto. Los cambios
        manuales aquí se conservan hasta la próxima sincronización.
      </p>

      {cargando && <StateMessage tipo="cargando" />}
      {!cargando && criterios.length === 0 && (
        <p className="criterios-admin__estado">
          No hay criterios todavía. Se cargarán automáticamente desde el
          proyecto cuando se actualicen.
        </p>
      )}

      <ul className="criterios-admin__lista">
        {criterios.map((c) => (
          <li key={c.id} className="criterios-admin__item">
            <div className="criterios-admin__cabecera">
              <strong>{c.nombre_archivo}</strong>
              <label className="criterios-admin__rec">
                <input
                  type="checkbox"
                  checked={editando === c.id ? recomendada : c.recomendada}
                  onChange={(e) => setRecomendada(e.target.checked)}
                  disabled={editando !== c.id}
                />
                Recomendada
              </label>
            </div>

            {editando === c.id ? (
              <>
                <textarea
                  className="textarea criterios-admin__texto"
                  aria-label={`Texto del criterio ${c.nombre_archivo}`}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  rows={8}
                />
                <input
                  className="input"
                  value={procedencia}
                  onChange={(e) => setProcedencia(e.target.value)}
                  placeholder="Procedencia (ej. criterio-vocal)"
                  aria-label="Procedencia"
                />
                <div className="criterios-admin__acciones">
                  <Button
                    size="sm"
                    onClick={() => void guardar(c.id)}
                    loading={guardando}
                  >
                    Guardar
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => cancelar(c)}
                    disabled={guardando}
                  >
                    Cancelar
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div
                  className="criterios-admin__contenido"
                  dangerouslySetInnerHTML={{
                    __html: renderMarkdown(stripFrontmatter(c.contenido_texto)),
                  }}
                />
                <div className="criterios-admin__acciones">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      toast("Descarga iniciada.", "success");
                      descargarObra(c.id);
                    }}
                  >
                    Descargar
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => iniciarEdicion(c)}
                    disabled={editando !== null}
                  >
                    Editar
                  </Button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={confirmDescartar}
        title="Descartar cambios"
        message="Los cambios al criterio no se guardaron y se van a perder."
        confirmLabel="Descartar"
        cancelLabel="Seguir editando"
        danger
        onConfirm={() => {
          setConfirmDescartar(false);
          setEditando(null);
        }}
        onCancel={() => setConfirmDescartar(false)}
      />
    </div>
  );
}
