// Expedientes — dashboard Sprint 4 (lista + detalle con obras).
//
// Marco-practico §3.4.7: el supervisor abre expedientes, carga obrados y
// administra el estado de publicación. El backend (AbrirExpediente,
// CargarObra, PublicarObra, ListarHistorialExpediente) llega en Sprint 4.
//
// Regla 5 (BLOQUEANTE): el backend aplica filtro de visibilidad en el
// adapter (ObraRepoImpl). El frontend NO envía usuario_id ni filtro de
// privacidad: solo pinta lo que el server devuelve. Obra propia = editable;
// obra publicada por otro = solo lectura.
//
// Diseño: dos vistas con estado local (sin router de frontend todavía).
//  1. Lista: DataTable de expedientes propios (paginado server-side).
//  2. Detalle: DataTable de obras del expediente seleccionado + acciones
//     (cargar obra, publicar obra propia).

import { useEffect, useRef, useState } from "react";

import DataTable, { type DataTableColumn } from "../../components/DataTable";
import ConfirmDialog from "../../components/ConfirmDialog";

import { useAuth } from "../../context/useAuth";
import { usePermisos } from "../../context/usePermisos";
import {
  promoverObraANorma,
  seleccionarFuente,
  type JerarquiaNorma,
} from "../../api/fuentes";
import { SubirFuenteForm } from "../../components/fuentes/SubirFuenteForm";
import type { EstadoTrabajo, Trabajo } from "../../api/jobs";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { useTrabajoIndexado } from "../../utils/useTrabajoIndexado";
import {
  Badge,
  Breadcrumb,
  Button,
  EstadoSwitch,
  Modal,
  PageHeader,
  SelectOtro,
  StateMessage,
} from "../../components/ui";

import {
  TIPO_DELITO,
  TIPO_PROCESO,
  GRADO_MILITAR,
  obtenerLabel,
} from "../../config/catalogos";

import {
  type AbrirExpedienteBody,
  type ExpedienteResumen,
  type ObraResumenDTO,
  type PaginaExpedientes,
  type RequisitosResp,
  abrirExpediente,
  cambiarEstadoExpediente,
  cargarObra,
  editarExpediente,
  eliminarObra,
  getRequisitos,
  listarExpedientes,
  listarHistorialExpediente,
  proponerPromocion,
  publicarObra,
  resolverPromocion,
} from "../../api/expedientes";
import {
  type BorradorDTO,
  TIPO_BORRADOR_LABEL,
  listarBorradores,
} from "../../api/borradores";
import {
  type DoctrinaDTO,
  descargarObra,
  listarDoctrinaPrivadaExpediente,
} from "../../api/doctrina";

import "./Expedientes.css";

const POR_PAGINA = 10;

// El tribunal de origen es SIEMPRE el TPJM: no es un campo editable.
const TRIBUNAL_FIJO = "Tribunal Permanente de Justicia Militar";

function badgeEstado(estado: string) {
  return (
    <Badge tone={estado === "activo" ? "info" : "neutral"}>{estado}</Badge>
  );
}

function badgeVisibilidad(v: string) {
  return v === "publicado" ? (
    <Badge tone="success">Publicado</Badge>
  ) : (
    <Badge tone="warning">Borrador</Badge>
  );
}

/** Autor de una obra: instancia inferior o usuario (nombre · cargo). */
function autorLegible(obra: ObraResumenDTO): string {
  if (obra.autor_instancia) return obra.autor_instancia;
  if (obra.autor_nombre) {
    return obra.autor_cargo
      ? `${obra.autor_nombre} · ${obra.autor_cargo}`
      : obra.autor_nombre;
  }
  return "—";
}

type Vista = { kind: "lista" } | { kind: "detalle"; expedienteId: number };

export default function Expedientes() {
  // Acciones según permisos efectivos (rol ⊕ overrides), no solo el rol.
  const { puede } = usePermisos();
  const puedeAbrir = puede("expedientes", "crear");
  const puedeEditar = puede("expedientes", "actualizar");

  const [vista, setVista] = useState<Vista>({ kind: "lista" });
  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<PaginaExpedientes | null>(null);
  const [texto, setTexto] = useState("");

  // Form apertura expediente
  const [abriendo, setAbriendo] = useState(false);
  // Progreso de la fase B: "Subiendo 2/5 · 40%".
  const [pasoAbrir, setPasoAbrir] = useState<string | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [archivosAbrir, setArchivosAbrir] = useState<
    { id: string; file: File; tipo: string }[]
  >([]);
  const [requisitos, setRequisitos] = useState<RequisitosResp | null>(null);
  const [requisitosError, setRequisitosError] = useState(false);
  const [formAbierto, setFormAbierto] = useState<AbrirExpedienteBody>({
    numero_caso: "",
    tipo_proceso: "consulta",
    tribunal_origen: TRIBUNAL_FIJO,
    procesado_nombre: "",
    procesado_grado: "",
    delito: "",
  });

  useEffect(() => {
    if (!formVisible) return;
    let cancel = false;
    setRequisitosError(false);
    getRequisitos(formAbierto.tipo_proceso)
      .then((r) => {
        if (!cancel) {
          setRequisitos(r);
          setRequisitosError(false);
        }
      })
      .catch(() => {
        if (!cancel) {
          setRequisitos(null);
          setRequisitosError(true);
        }
      });
    return () => {
      cancel = true;
    };
  }, [formAbierto.tipo_proceso, formVisible]);

  useEffect(() => {
    if (vista.kind !== "lista") return;
    let cancelado = false;
    setData(null);
    listarExpedientes({ pagina, por_pagina: POR_PAGINA })
      .then((resp) => {
        if (!cancelado) setData(resp);
      })
      .catch((err) => {
        if (!cancelado)
          toast(
            mensajeError(err, "No se pudo cargar la lista de expedientes."),
            "error",
          );
      });
    return () => {
      cancelado = true;
    };
  }, [vista, pagina]);

  function resetForm() {
    setFormAbierto({
      numero_caso: "",
      tipo_proceso: "consulta",
      tribunal_origen: TRIBUNAL_FIJO,
      procesado_nombre: "",
      procesado_grado: "",
      delito: "",
    });
    setFormVisible(false);
    setAbriendo(false);
    setArchivosAbrir([]);
  }

  // Cancelar la apertura con datos cargados pide confirmación.
  const [confirmDescartar, setConfirmDescartar] = useState(false);
  const aperturaConDatos =
    archivosAbrir.length > 0 ||
    formAbierto.numero_caso !== "" ||
    formAbierto.procesado_nombre !== "" ||
    formAbierto.procesado_grado !== "" ||
    formAbierto.delito !== "";
  function cancelarApertura() {
    if (aperturaConDatos) setConfirmDescartar(true);
    else resetForm();
  }

  // Tipos seleccionados por archivo (para validación por tipo real)
  const tiposSeleccionados = new Set(archivosAbrir.map((a) => a.tipo));
  const faltantesReales =
    requisitos !== null
      ? requisitos.requeridos.filter((r) => !tiposSeleccionados.has(r))
      : [];

  async function submitAbrir(e: React.FormEvent) {
    e.preventDefault();
    setAbriendo(true);

    // Fase A — crear expediente. Si falla acá es error total (403/409/red):
    // no se creó nada, el modal queda abierto para corregir y reintentar.
    let resp: Awaited<ReturnType<typeof abrirExpediente>>;
    try {
      resp = await abrirExpediente(formAbierto);
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response
        ?.status;
      const mensaje =
        status === 403
          ? "No tenés permisos para abrir expedientes. Solo el supervisor puede hacerlo."
          : status === 409
            ? `Ya existe un expediente con el Nº de caso ${formAbierto.numero_caso}.`
            : mensajeError(err, "No se pudo abrir el expediente.");
      toast(mensaje, "error");
      setAbriendo(false);
      return;
    }

    // Fase B — cargar obras tolerante: un archivo fallido no cancela los
    // demás ni oculta que el expediente YA existe (retry daría 409).
    const autorInstancia = formAbierto.tribunal_origen.trim();
    const fallidos: string[] = [];
    for (const [i, { file, tipo }] of archivosAbrir.entries()) {
      const paso = `Subiendo ${i + 1}/${archivosAbrir.length}`;
      setPasoAbrir(paso);
      try {
        await cargarObra({
          expediente_id: resp.expediente_id,
          file,
          tipo_documento: tipo,
          autor_instancia: autorInstancia,
          onProgreso: (pct) => setPasoAbrir(`${paso} · ${pct}%`),
        });
      } catch (err) {
        fallidos.push(`${file.name}: ${mensajeError(err, "error al cargar")}`);
      }
    }

    if (fallidos.length === 0) {
      toast("Expediente abierto correctamente.", "success");
    } else {
      toast(
        `Expediente ${resp.numero_caso} creado con ${
          archivosAbrir.length - fallidos.length
        }/${archivosAbrir.length} obrados. Fallaron: ${fallidos.join("; ")}. Completalos desde 'Ver obrados'.`,
        "warning",
      );
    }
    setPasoAbrir(null);
    resetForm();
    // Refetch explícito: setPagina(1) no re-dispara el effect si ya está
    // en la página 1, dejando la lista desactualizada.
    listarExpedientes({ pagina: 1, por_pagina: POR_PAGINA })
      .then((listaResp) => setData(listaResp))
      .catch(() => undefined);
    setPagina(1);
  }

  // Form edición expediente
  const [expedienteEditando, setExpedienteEditando] =
    useState<ExpedienteResumen | null>(null);
  const [editForm, setEditForm] = useState({
    numero_caso: "",
    procesado_nombre: "",
    delito: "",
    tribunal_origen: "",
  });
  const [guardandoEdit, setGuardandoEdit] = useState(false);

  function abrirEdicion(exp: ExpedienteResumen) {
    setExpedienteEditando(exp);
    setEditForm({
      numero_caso: exp.numero_caso,
      procesado_nombre: exp.procesado_nombre,
      delito: exp.delito,
      tribunal_origen: exp.tribunal_origen ?? TRIBUNAL_FIJO,
    });
  }

  function submitEditar(e: React.FormEvent) {
    e.preventDefault();
    if (!expedienteEditando) return;
    setGuardandoEdit(true);
    editarExpediente(expedienteEditando.id, editForm)
      .then(() => {
        toast("Expediente modificado correctamente.", "success");
        setExpedienteEditando(null);
        return listarExpedientes({ pagina, por_pagina: POR_PAGINA });
      })
      .then((resp) => setData(resp))
      .catch((err) =>
        toast(mensajeError(err, "No se pudo editar el expediente."), "error"),
      )
      .finally(() => setGuardandoEdit(false));
  }

  const rowsFiltrados =
    data?.items.filter((i) =>
      texto.trim() === ""
        ? true
        : i.numero_caso.toLowerCase().includes(texto.toLowerCase()) ||
          i.procesado_nombre.toLowerCase().includes(texto.toLowerCase()),
    ) ?? null;

  const [cambiandoEstado, setCambiandoEstado] = useState<number | null>(null);

  function toggleEstado(exp: ExpedienteResumen) {
    if (cambiandoEstado !== null) return;
    const nuevo = exp.estado === "activo" ? "archivado" : "activo";
    setCambiandoEstado(exp.id);
    cambiarEstadoExpediente(exp.id, nuevo)
      .then(() => listarExpedientes({ pagina, por_pagina: POR_PAGINA }))
      .then((resp) => setData(resp))
      .catch((err) =>
        toast(mensajeError(err, "No se pudo cambiar el estado."), "error"),
      )
      .finally(() => setCambiandoEstado(null));
  }

  if (vista.kind === "detalle") {
    return (
      <DetalleExpediente
        expedienteId={vista.expedienteId}
        numeroCaso={
          data?.items.find((e) => e.id === vista.expedienteId)?.numero_caso
        }
        onVolver={() => setVista({ kind: "lista" })}
      />
    );
  }

  return (
    <div className="expedientes">
      <PageHeader
        title="Expedientes"
        subtitle="Apertura y gestión de expedientes judiciales."
        actions={
          puedeAbrir ? (
            <Button
              onClick={() =>
                formVisible ? cancelarApertura() : setFormVisible(true)
              }
              disabled={abriendo}
            >
              {formVisible ? "Cancelar" : "+ Abrir expediente"}
            </Button>
          ) : undefined
        }
      />

      {puedeAbrir && formVisible && (
        <form className="expedientes__form" onSubmit={submitAbrir}>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="abrir-numero">
              Nº de caso *
            </label>
            <input
              id="abrir-numero"
              className="input"
              required
              value={formAbierto.numero_caso}
              onChange={(e) =>
                setFormAbierto({ ...formAbierto, numero_caso: e.target.value })
              }
            />
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="abrir-tipo">
              Tipo de proceso *
            </label>
            <select
              id="abrir-tipo"
              className="select"
              value={formAbierto.tipo_proceso}
              onChange={(e) =>
                setFormAbierto({
                  ...formAbierto,
                  tipo_proceso: e.target
                    .value as AbrirExpedienteBody["tipo_proceso"],
                })
              }
            >
              {TIPO_PROCESO.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="abrir-tribunal">
              Tribunal de origen *
            </label>
            <input
              id="abrir-tribunal"
              className="input"
              value={TRIBUNAL_FIJO}
              readOnly
            />
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="abrir-procesado">
              Nombre del procesado *
            </label>
            <input
              id="abrir-procesado"
              className="input"
              required
              value={formAbierto.procesado_nombre}
              onChange={(e) =>
                setFormAbierto({
                  ...formAbierto,
                  procesado_nombre: e.target.value,
                })
              }
            />
          </div>
          <div className="expedientes__field">
            <SelectOtro
              id="abrir-grado"
              label="Grado militar"
              opciones={GRADO_MILITAR}
              value={formAbierto.procesado_grado ?? ""}
              onChange={(v) =>
                setFormAbierto({ ...formAbierto, procesado_grado: v || null })
              }
            />
          </div>
          <div className="expedientes__field">
            <SelectOtro
              id="abrir-delito"
              label="Delito *"
              opciones={TIPO_DELITO}
              value={formAbierto.delito}
              onChange={(v) => setFormAbierto({ ...formAbierto, delito: v })}
              required
            />
          </div>
          <h3 className="expedientes__subtitulo">Obrados de entrada</h3>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="abrir-archivos">
              Archivos de la instancia inferior
            </label>
            <input
              id="abrir-archivos"
              type="file"
              multiple
              accept=".pdf,.doc,.docx"
              className="expedientes__file"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                const nuevos = files.map((file, idx) => ({
                  id: `${Date.now()}-${idx}-${file.name}`,
                  file,
                  // Prefill solo mientras alcance el orden de requisitos;
                  // archivos extra nacen 'otro' para no duplicar la pieza.
                  tipo: requisitos?.requeridos[idx] ?? "otro",
                }));
                setArchivosAbrir(nuevos);
              }}
            />
            <span className="expedientes__hint">
              {archivosAbrir.length > 0
                ? `${archivosAbrir.length} archivo(s) a cargar con autor "${formAbierto.tribunal_origen.trim() || "la instancia inferior"}"`
                : "Adjuntá los obrados remitidos por la instancia inferior (autor = tribunal de origen)."}
            </span>
          </div>
          {archivosAbrir.length > 0 && (
            <div className="expedientes__field">
              <span className="expedientes__label">Tipo por archivo</span>
              {archivosAbrir.map((a) => (
                <div key={a.id} className="expedientes__archivo-row">
                  <span
                    className="expedientes__archivo-nombre"
                    title={a.file.name}
                  >
                    {a.file.name}
                  </span>
                  <select
                    className="select expedientes__archivo-select"
                    aria-label={`Tipo de documento — ${a.file.name}`}
                    value={a.tipo}
                    onChange={(e) =>
                      setArchivosAbrir((prev) =>
                        prev.map((p) =>
                          p.id === a.id ? { ...p, tipo: e.target.value } : p,
                        ),
                      )
                    }
                  >
                    <option value="sentencia">Sentencia</option>
                    <option value="acta_audiencia">Acta de Audiencia</option>
                    <option value="oficio_elevacion">
                      Oficio de Elevación
                    </option>
                    <option value="auto_interlocutorio">
                      Auto Interlocutorio
                    </option>
                    <option value="memorial_apelacion">
                      Memorial de Apelación
                    </option>
                    <option value="otro">Otro</option>
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    onClick={() =>
                      setArchivosAbrir((prev) =>
                        prev.filter((p) => p.id !== a.id),
                      )
                    }
                    aria-label={`Quitar ${a.file.name}`}
                  >
                    Quitar
                  </Button>
                </div>
              ))}
            </div>
          )}
          {requisitosError && (
            <div
              className="expedientes__alert expedientes__alert--error"
              role="alert"
            >
              <strong className="expedientes__alert-titulo">
                No se pudieron cargar los requisitos. No se puede aperturar
                hasta reintentar.
              </strong>
            </div>
          )}
          {requisitos && !requisitosError && (
            <div
              className="expedientes__alert expedientes__alert--warning"
              role="status"
              aria-live="polite"
            >
              <strong className="expedientes__alert-titulo">
                Requisitos para {formAbierto.tipo_proceso}:
              </strong>
              <ul className="expedientes__alert-lista">
                {requisitos.nombres.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
              {faltantesReales.length > 0 && (
                <span className="expedientes__alert-aviso expedientes__alert-aviso--pendiente">
                  Te faltan:{" "}
                  {faltantesReales
                    .map(
                      (t) =>
                        requisitos.nombres[requisitos.requeridos.indexOf(t)],
                    )
                    .join(", ")}
                  . El expediente no se creará hasta completar los requeridos —
                  el modal quedará abierto.
                </span>
              )}
              {faltantesReales.length === 0 && archivosAbrir.length > 0 && (
                <span className="expedientes__alert-aviso expedientes__alert-aviso--ok">
                  Cubrís el mínimo requerido. Podés aperturar.
                </span>
              )}
            </div>
          )}
          <div className="expedientes__form-actions">
            <Button
              variant="secondary"
              onClick={cancelarApertura}
              disabled={abriendo}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={
                abriendo ||
                requisitosError ||
                (requisitos !== null && faltantesReales.length > 0) ||
                (requisitos !== null && archivosAbrir.length === 0)
              }
              title={
                requisitosError
                  ? "No se pudieron cargar requisitos"
                  : requisitos !== null && faltantesReales.length > 0
                    ? `Faltan: ${faltantesReales.map((t) => requisitos.nombres[requisitos.requeridos.indexOf(t)]).join(", ")}`
                    : undefined
              }
            >
              {abriendo ? (pasoAbrir ?? "Abriendo...") : "Abrir"}
            </Button>
          </div>
        </form>
      )}

      <ConfirmDialog
        open={confirmDescartar}
        title="Descartar apertura"
        message="Se perderán los datos y archivos cargados del expediente nuevo."
        confirmLabel="Descartar"
        cancelLabel="Seguir editando"
        danger
        onConfirm={() => {
          setConfirmDescartar(false);
          resetForm();
        }}
        onCancel={() => setConfirmDescartar(false)}
      />

      {puedeEditar && expedienteEditando !== null && (
        <form className="expedientes__form" onSubmit={submitEditar}>
          <h3>Editar expediente #{expedienteEditando.id}</h3>
          <div className="expedientes__field">
            <label className="expedientes__label">Nº de caso</label>
            <input
              className="input"
              value={editForm.numero_caso}
              onChange={(e) =>
                setEditForm({ ...editForm, numero_caso: e.target.value })
              }
            />
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label">Procesado</label>
            <input
              className="input"
              value={editForm.procesado_nombre}
              onChange={(e) =>
                setEditForm({ ...editForm, procesado_nombre: e.target.value })
              }
            />
          </div>
          <div className="expedientes__field">
            <SelectOtro
              id="editar-delito"
              label="Delito"
              opciones={TIPO_DELITO}
              value={editForm.delito}
              onChange={(v) => setEditForm({ ...editForm, delito: v })}
            />
          </div>
          <div className="expedientes__form-actions">
            <Button
              variant="secondary"
              onClick={() => setExpedienteEditando(null)}
              disabled={guardandoEdit}
            >
              Cancelar
            </Button>
            <Button variant="primary" type="submit" disabled={guardandoEdit}>
              {guardandoEdit ? "Guardando..." : "Guardar cambios"}
            </Button>
          </div>
        </form>
      )}

      <DataTable<ExpedienteResumen>
        columns={columnasExpedientes(
          (id) => setVista({ kind: "detalle", expedienteId: id }),
          abrirEdicion,
          puedeEditar,
          toggleEstado,
          cambiandoEstado,
        )}
        rowKey={(r) => r.id}
        numerada
        rows={rowsFiltrados}
        total={data?.total ?? null}
        page={pagina}
        pageSize={POR_PAGINA}
        onPageChange={setPagina}
        searchPlaceholder="Buscar por nº caso o procesado..."
        searchValue={texto}
        onSearchChange={(v) => setTexto(v)}
        emptyMessage="No hay expedientes. Abrí uno con el botón superior."
      />
    </div>
  );
}

function columnasExpedientes(
  onAbrir: (id: number) => void,
  onEditar: (exp: ExpedienteResumen) => void,
  puedeEditar: boolean,
  onToggleEstado: (exp: ExpedienteResumen) => void,
  cambiandoId: number | null,
): DataTableColumn<ExpedienteResumen>[] {
  return [
    { key: "numero_caso", header: "Nº de caso" },
    {
      key: "tipo_proceso",
      header: "Tipo",
      render: (r) => obtenerLabel(TIPO_PROCESO, r.tipo_proceso),
    },
    { key: "procesado_nombre", header: "Procesado" },
    { key: "delito", header: "Delito" },
    {
      key: "fojas_total",
      header: "Fojas",
      render: (r) => r.fojas_total ?? "—",
    },
    {
      key: "estado",
      header: "Estado",
      render: (r) =>
        puedeEditar ? (
          <EstadoSwitch
            activo={r.estado === "activo"}
            disabled={cambiandoId === r.id}
            etiquetas={["Activo", "Archivado"]}
            ariaLabel={`Cambiar estado del expediente ${r.numero_caso}`}
            onChange={() => onToggleEstado(r)}
          />
        ) : (
          badgeEstado(r.estado)
        ),
    },
    {
      key: "created_at",
      header: "Abierto",
      render: (r) =>
        r.created_at !== null
          ? new Date(r.created_at).toLocaleDateString()
          : "—",
    },
    {
      key: "_acciones",
      header: "Acciones",
      render: (r) => (
        <div className="expedientes__acciones">
          {puedeEditar && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => onEditar(r)}
              aria-label={`Editar expediente ${r.numero_caso}`}
            >
              Editar
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => onAbrir(r.id)}
            aria-label={`Ver expediente ${r.numero_caso}`}
          >
            Ver obrados →
          </Button>
        </div>
      ),
    },
  ];
}

// ---------- Detalle de expediente (lista de obras + acciones) ----------

interface DetalleProps {
  expedienteId: number;
  numeroCaso?: string | null;
  onVolver: () => void;
}

function DetalleExpediente({
  expedienteId,
  numeroCaso,
  onVolver,
}: DetalleProps) {
  const { auth: authDetalle } = useAuth();
  const esSupervisorDetalle = authDetalle?.rol === "supervisor";
  const { puede } = usePermisos();
  // Resumen del expediente (para PageHeader/subtitle con N° real).
  const [resumen, setResumen] = useState<ExpedienteResumen | null>(null);
  useEffect(() => {
    let cancelado = false;
    listarExpedientes({ pagina: 1, por_pagina: 100 })
      .then((resp) => {
        if (!cancelado) {
          const propio = resp.items.find((e) => e.id === expedienteId) ?? null;
          setResumen(propio);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelado = true;
    };
  }, [expedienteId]);
  const [obras, setObras] = useState<ObraResumenDTO[] | null>(null);
  const [borradoresPublicados, setBorradoresPublicados] = useState<
    BorradorDTO[]
  >([]);
  const [doctrinasPrivadas, setDoctrinasPrivadas] = useState<
    DoctrinaDTO[] | null
  >(null);
  const [cargandoObra, setCargandoObra] = useState(false);
  const [progresoObra, setProgresoObra] = useState(0);
  const [errorObra, setErrorObra] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [subirDoctrinaVisible, setSubirDoctrinaVisible] = useState(false);
  const [promoverNorma, setPromoverNorma] = useState<ObraResumenDTO | null>(
    null,
  );
  const [normaNombre, setNormaNombre] = useState("");
  const [normaJerarquia, setNormaJerarquia] =
    useState<JerarquiaNorma>("supletoria");
  const [confirmPublicar, setConfirmPublicar] = useState<ObraResumenDTO | null>(
    null,
  );
  const [confirmEliminar, setConfirmEliminar] = useState<ObraResumenDTO | null>(
    null,
  );
  const [file, setFile] = useState<File | null>(null);
  const [tipoDocumento, setTipoDocumento] = useState("sentencia");
  const [fojasInicio, setFojasInicio] = useState<string>("");
  const [fojasFin, setFojasFin] = useState<string>("");
  const [publicando, setPublicando] = useState<number | null>(null);
  const [promoviendo, setPromoviendo] = useState<number | null>(null);
  const trabajoNorma = useTrabajoIndexado();
  const [eliminandoObra, setEliminandoObra] = useState<number | null>(null);

  useEffect(() => {
    let cancelado = false;
    setObras(null);
    listarHistorialExpediente(expedienteId)
      .then((resp) => {
        if (!cancelado) setObras(resp.obras);
      })
      .catch((err) => {
        if (!cancelado)
          toast(
            mensajeError(err, "No se pudo cargar el historial de obrados."),
            "error",
          );
      });
    // Borradores publicados del expediente (Regla 7: publicados visibles).
    listarBorradores(expedienteId)
      .then((items) => {
        if (!cancelado)
          setBorradoresPublicados(
            items.filter((b) => b.estado === "publicado"),
          );
      })
      .catch(() => {
        if (!cancelado) setBorradoresPublicados([]);
      });
    // Doctrina privada del expediente.
    listarDoctrinaPrivadaExpediente(expedienteId)
      .then((items) => {
        if (!cancelado) setDoctrinasPrivadas(items);
      })
      .catch(() => {
        if (!cancelado) setDoctrinasPrivadas([]);
      });
    return () => {
      cancelado = true;
    };
  }, [expedienteId]);

  function submitCargar(e: React.FormEvent) {
    e.preventDefault();
    if (file === null) {
      toast("Seleccioná un archivo.", "warning");
      return;
    }
    setCargandoObra(true);
    setProgresoObra(0);
    setErrorObra(null);
    cargarObra({
      expediente_id: expedienteId,
      file,
      tipo_documento: tipoDocumento,
      fojas_inicio: fojasInicio === "" ? undefined : Number(fojasInicio),
      fojas_fin: fojasFin === "" ? undefined : Number(fojasFin),
      onProgreso: setProgresoObra,
    })
      .then(() => {
        toast("Obrado cargado correctamente.", "success");
        setFile(null);
        if (fileRef.current) fileRef.current.value = "";
        setFojasInicio("");
        setFojasFin("");
        // re-fetch obras
        return listarHistorialExpediente(expedienteId);
      })
      .then((resp) => setObras(resp.obras))
      .catch((err) => {
        const msg = mensajeError(err, "No se pudo cargar el obrado.");
        setErrorObra(msg);
        toast(msg, "error");
      })
      .finally(() => setCargandoObra(false));
  }

  function publicar(obra: ObraResumenDTO) {
    setConfirmPublicar(obra);
  }

  function eliminar(obra: ObraResumenDTO) {
    setConfirmEliminar(obra);
  }

  function confirmarPublicar() {
    if (confirmPublicar === null) return;
    const obra = confirmPublicar;
    setConfirmPublicar(null);
    setPublicando(obra.id);
    publicarObra(expedienteId, obra.id)
      .then(() => {
        toast("Obrado publicado correctamente.", "success");
        return listarHistorialExpediente(expedienteId);
      })
      .then((resp) => setObras(resp.obras))
      .catch((err) =>
        toast(mensajeError(err, "No se pudo publicar el obrado."), "error"),
      )
      .finally(() => setPublicando(null));
  }

  /** Operador: propone; supervisor: promueve (o aprueba la propuesta). */
  function promoverObra(obra: ObraResumenDTO) {
    setPromoviendo(obra.id);
    const accion = esSupervisorDetalle
      ? resolverPromocion(expedienteId, obra.id, true)
      : proponerPromocion(expedienteId, obra.id);
    accion
      .then(() => {
        toast(
          esSupervisorDetalle
            ? "Obrado promovido a jurisprudencia."
            : "Promoción propuesta: queda pendiente de aprobación.",
          "success",
        );
        return listarHistorialExpediente(expedienteId);
      })
      .then((resp) => setObras(resp.obras))
      .catch((err) =>
        toast(mensajeError(err, "No se pudo promover el obrado."), "error"),
      )
      .finally(() => setPromoviendo(null));
  }

  function confirmarEliminarObra() {
    if (confirmEliminar === null) return;
    const obra = confirmEliminar;
    setConfirmEliminar(null);
    setEliminandoObra(obra.id);
    eliminarObra(expedienteId, obra.id)
      .then(() => {
        toast("Obrado eliminado correctamente.", "success");
        return listarHistorialExpediente(expedienteId);
      })
      .then((resp) => setObras(resp.obras))
      .catch((err) =>
        toast(mensajeError(err, "No se pudo eliminar el obrado."), "error"),
      )
      .finally(() => setEliminandoObra(null));
  }

  /** Libro subido: se fija de inmediato a este expediente (puntero privado). */
  function libroSubido(trabajo: Trabajo) {
    setSubirDoctrinaVisible(false);
    const normaId = trabajo.resultado?.norma_id;
    if (typeof normaId !== "number") return;
    seleccionarFuente(normaId, expedienteId)
      .then(() => listarDoctrinaPrivadaExpediente(expedienteId))
      .then((items) => setDoctrinasPrivadas(items))
      .catch((err) =>
        toast(
          mensajeError(err, "No se pudo fijar el libro al expediente."),
          "error",
        ),
      );
  }

  async function confirmarPromoverNorma() {
    if (promoverNorma === null || normaNombre.trim().length < 3) return;
    const obra = promoverNorma;
    setPromoviendo(obra.id);
    try {
      const encolado = await promoverObraANorma(
        obra.id,
        normaNombre.trim(),
        normaJerarquia,
      );
      const final = await trabajoNorma.seguir(
        encolado.job_id,
        encolado.estado as EstadoTrabajo,
      );
      if (final === null) return; // desmontado mientras seguía el trabajo
      if (final.estado === "completado") {
        toast(
          esSupervisorDetalle
            ? "Obrado promovido a norma del corpus."
            : "Promoción a norma propuesta: queda pendiente de aprobación.",
          "success",
        );
        setPromoverNorma(null);
        setNormaNombre("");
        const resp = await listarHistorialExpediente(expedienteId);
        setObras(resp.obras);
      } else if (final.estado === "cancelado") {
        toast("Promoción a norma cancelada.", "info");
      } else {
        toast(final.error ?? "No se pudo promover a norma.", "error");
      }
    } catch (err) {
      toast(mensajeError(err, "No se pudo promover a norma."), "error");
    } finally {
      setPromoviendo(null);
    }
  }

  async function cancelarPromoverNorma() {
    try {
      await trabajoNorma.cancelar();
      toast("Cancelando la promoción…", "info");
    } catch (err) {
      toast(mensajeError(err, "No se pudo cancelar la promoción."), "error");
    }
  }

  return (
    <div className="expedientes">
      <Breadcrumb
        items={[
          { label: "Expedientes", onClick: onVolver },
          { label: `Nº ${numeroCaso ?? resumen?.numero_caso ?? expedienteId}` },
        ]}
      />

      <PageHeader
        title="Obrados del expediente"
        subtitle={
          resumen
            ? `Expediente N° ${resumen.numero_caso} — ${resumen.procesado_nombre}`
            : `Expediente #${expedienteId}`
        }
      />

      {/* Cargar obra */}
      {puede("obras", "crear") && (
        <form className="expedientes__form" onSubmit={submitCargar}>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="obra-file">
              Archivo *
            </label>
            <input
              id="obra-file"
              ref={fileRef}
              type="file"
              className="expedientes__file"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="obra-tipo">
              Tipo de documento *
            </label>
            <select
              id="obra-tipo"
              className="select"
              value={tipoDocumento}
              onChange={(e) => setTipoDocumento(e.target.value)}
            >
              <option value="sentencia">Sentencia</option>
              <option value="memorial_apelacion">Memorial de Apelación</option>
              <option value="auto_interlocutorio">Auto Interlocutorio</option>
              <option value="oficio_elevacion">Oficio de Elevación</option>
              <option value="acta_audiencia">Acta de Audiencia</option>
              <option value="requerimiento_fiscal">Requerimiento Fiscal</option>
              <option value="dictamen_radicatoria">
                Dictamen de Radicatoria
              </option>
              <option value="dictamen_fondo">Dictamen de Fondo</option>
              <option value="relacion_obrados">Relación de Obrados</option>
              <option value="proyecto_auto_vista">
                Proyecto de Auto de Vista
              </option>
              <option value="auto_vista">Auto de Vista</option>
              <option value="otro">Otro</option>
            </select>
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="obra-fojas-i">
              Fojas inicio (opcional)
            </label>
            <input
              id="obra-fojas-i"
              type="number"
              min={1}
              className="input"
              value={fojasInicio}
              onChange={(e) => setFojasInicio(e.target.value)}
            />
          </div>
          <div className="expedientes__field">
            <label className="expedientes__label" htmlFor="obra-fojas-f">
              Fojas fin (opcional)
            </label>
            <input
              id="obra-fojas-f"
              type="number"
              min={1}
              className="input"
              value={fojasFin}
              onChange={(e) => setFojasFin(e.target.value)}
            />
            <span className="expedientes__hint">
              Número de hoja en el expediente físico.
            </span>
          </div>
          <div className="expedientes__form-actions">
            <Button
              variant="primary"
              type="submit"
              disabled={cargandoObra}
              aria-busy={cargandoObra}
            >
              {cargandoObra
                ? progresoObra < 100
                  ? `Subiendo ${progresoObra}%`
                  : "Procesando…"
                : "Cargar obrado"}
            </Button>
          </div>
          {errorObra && <StateMessage tipo="error">{errorObra}</StateMessage>}
        </form>
      )}

      <ConfirmDialog
        open={confirmPublicar !== null}
        title="Publicar obrado"
        message={
          <>
            ¿Publicar el obrado{" "}
            <strong>{confirmPublicar?.nombre_archivo}</strong>? Una vez
            publicada será visible para otros operadores.
          </>
        }
        confirmLabel="Publicar"
        cancelLabel="Cancelar"
        danger
        busy={publicando === confirmPublicar?.id}
        onConfirm={confirmarPublicar}
        onCancel={() => setConfirmPublicar(null)}
      />

      <Modal
        open={promoverNorma !== null}
        title={
          esSupervisorDetalle
            ? "Promover a norma del corpus"
            : "Proponer como norma del corpus"
        }
        onClose={() => setPromoverNorma(null)}
        busy={promoviendo !== null}
        footer={
          <>
            {trabajoNorma.enCurso && (
              <Button
                variant="secondary"
                onClick={() => void cancelarPromoverNorma()}
                disabled={trabajoNorma.cancelando}
              >
                {trabajoNorma.cancelando ? "Cancelando…" : "Cancelar indexado"}
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={() => setPromoverNorma(null)}
              disabled={trabajoNorma.enCurso}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={() => void confirmarPromoverNorma()}
              disabled={
                normaNombre.trim().length < 3 ||
                promoviendo !== null ||
                trabajoNorma.enCurso
              }
            >
              {trabajoNorma.enCurso
                ? "Indexando…"
                : esSupervisorDetalle
                  ? "Promover"
                  : "Proponer"}
            </Button>
          </>
        }
      >
        <p>
          <strong>{promoverNorma?.nombre_archivo}</strong> se indexará por
          artículos como una norma.{" "}
          {esSupervisorDetalle
            ? "Quedará global de inmediato."
            : "Quedará pendiente hasta que el supervisor la apruebe."}
        </p>
        {trabajoNorma.enCurso && (
          <p className="expedientes__hint">
            Indexando: podés cancelarlo, y se detiene al terminar la fase en
            curso.
          </p>
        )}
        <div className="expedientes__field">
          <label className="expedientes__label" htmlFor="norma-nombre">
            Nombre de la norma
          </label>
          <input
            id="norma-nombre"
            className="input"
            value={normaNombre}
            onChange={(e) => setNormaNombre(e.target.value)}
          />
        </div>
        <div className="expedientes__field">
          <label className="expedientes__label" htmlFor="norma-jerarquia">
            Jerarquía
          </label>
          <select
            id="norma-jerarquia"
            className="input"
            value={normaJerarquia}
            onChange={(e) =>
              setNormaJerarquia(e.target.value as JerarquiaNorma)
            }
          >
            <option value="suprema">Suprema</option>
            <option value="militar">Militar</option>
            <option value="supletoria">Supletoria</option>
          </select>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmEliminar !== null}
        title="Eliminar obrado"
        message={
          <>
            ¿Eliminar el obrado{" "}
            <strong>{confirmEliminar?.nombre_archivo}</strong>? Esta acción
            limpiará sus fragmentos y vectores de forma permanente.
          </>
        }
        confirmLabel="Eliminar"
        cancelLabel="Cancelar"
        danger
        busy={eliminandoObra === confirmEliminar?.id}
        onConfirm={confirmarEliminarObra}
        onCancel={() => setConfirmEliminar(null)}
      />

      <DataTable<ObraResumenDTO>
        columns={columnasObras(
          publicar,
          eliminar,
          publicando,
          eliminandoObra,
          promoverObra,
          promoviendo,
          esSupervisorDetalle,
          (obra) => setPromoverNorma(obra),
          {
            actualizar: puede("obras", "actualizar"),
            eliminar: puede("obras", "eliminar"),
          },
        )}
        rowKey={(r) => r.id}
        numerada
        rows={obras}
        emptyMessage="No hay obrados cargados en este expediente."
      />

      {/* Doctrina privada del expediente */}
      <section
        className="expedientes__publicados"
        aria-label="Doctrina del expediente"
      >
        <div className="expedientes__seccion-header">
          <h3 className="expedientes__publicados-titulo">
            Doctrina del expediente
          </h3>
          {puede("doctrina", "crear") && (
            <Button
              variant="secondary"
              onClick={() => setSubirDoctrinaVisible((v) => !v)}
            >
              {subirDoctrinaVisible
                ? "Cancelar subida"
                : "+ Subir doctrina (libro)"}
            </Button>
          )}
        </div>

        {subirDoctrinaVisible && (
          <SubirFuenteForm
            categoria="doctrina"
            esSupervisor={esSupervisorDetalle}
            onSubida={libroSubido}
          />
        )}

        <DataTable<DoctrinaDTO>
          columns={columnasDoctrina((id) => {
            toast("Descarga iniciada.", "success");
            descargarObra(id);
          })}
          rowKey={(r) => r.id}
          numerada
          rows={doctrinasPrivadas}
          emptyMessage="No hay doctrina fijada en este expediente."
        />
      </section>

      {borradoresPublicados.length > 0 && (
        <section
          className="expedientes__publicados"
          aria-label="Obrados publicados"
        >
          <h3 className="expedientes__publicados-titulo">Obrados publicados</h3>
          <ul className="expedientes__publicados-lista">
            {borradoresPublicados.map((b) => (
              <li key={b.id} className="expedientes__publicado">
                <span className="expedientes__publicado-tipo">
                  {TIPO_BORRADOR_LABEL[
                    b.tipo as keyof typeof TIPO_BORRADOR_LABEL
                  ] ?? b.tipo}
                </span>
                <span className="expedientes__publicado-autor">
                  {b.autor_nombre
                    ? b.autor_cargo
                      ? `${b.autor_nombre} · ${b.autor_cargo}`
                      : b.autor_nombre
                    : "—"}
                  {" · "}
                  <Badge
                    tone={
                      b.estado === "publicado" || b.estado === "oficial"
                        ? "success"
                        : b.estado === "pendiente_oficial"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {b.estado === "pendiente_oficial"
                      ? "Pendiente de oficial"
                      : b.estado}
                  </Badge>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function columnasObras(
  onPublicar: (obra: ObraResumenDTO) => void,
  onEliminar: (obra: ObraResumenDTO) => void,
  publicandoId: number | null,
  eliminandoId: number | null,
  onPromover: (obra: ObraResumenDTO) => void,
  promoviendoId: number | null,
  esSupervisor: boolean,
  onPromoverNorma: (obra: ObraResumenDTO) => void,
  permisoObras: { actualizar: boolean; eliminar: boolean },
): DataTableColumn<ObraResumenDTO>[] {
  return [
    { key: "nombre_archivo", header: "Archivo" },
    { key: "tipo_documento", header: "Tipo" },
    {
      key: "autor",
      header: "Autor",
      render: (r) => autorLegible(r),
    },
    {
      key: "estado_visibilidad",
      header: "Visibilidad",
      render: (r) => badgeVisibilidad(r.estado_visibilidad),
    },
    {
      key: "es_propia",
      header: "Propia",
      render: (r) => (r.es_propia ? "Sí" : "No"),
    },
    {
      key: "created_at_iso",
      header: "Cargada",
      render: (r) => new Date(r.created_at_iso).toLocaleDateString(),
    },
    {
      key: "_acciones",
      header: "Acciones",
      render: (r) => (
        <div className="expedientes__acciones">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => {
              toast("Descarga iniciada.", "success");
              descargarObra(r.id);
            }}
          >
            Descargar
          </Button>
          {permisoObras.actualizar &&
            r.es_propia &&
            r.estado_visibilidad !== "publicado" && (
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => onPublicar(r)}
                disabled={publicandoId === r.id}
              >
                {publicandoId === r.id ? "Publicando..." : "Publicar"}
              </Button>
            )}
          {r.estado_validacion === "promocion_pendiente" && (
            <Badge tone="info">Propuesto a jurisprudencia</Badge>
          )}
          {r.estado_validacion === "promovida" && (
            <Badge tone="success">Jurisprudencia</Badge>
          )}
          {r.estado_validacion === "promovida_a_norma" && (
            <Badge tone="success">Norma</Badge>
          )}
          {permisoObras.actualizar && puedePromoverANorma(r, esSupervisor) && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => onPromoverNorma(r)}
              title={
                esSupervisor
                  ? undefined
                  : "Queda pendiente hasta que un supervisor la apruebe"
              }
            >
              {esSupervisor ? "Promover a norma" : "Proponer como norma"}
            </Button>
          )}
          {permisoObras.actualizar && puedePromover(r, esSupervisor) && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => onPromover(r)}
              disabled={promoviendoId === r.id}
              title={
                esSupervisor
                  ? undefined
                  : "Queda pendiente hasta que un supervisor la apruebe"
              }
            >
              {promoviendoId === r.id
                ? esSupervisor
                  ? "Promoviendo..."
                  : "Proponiendo..."
                : esSupervisor
                  ? "Promover a jurisprudencia"
                  : "Proponer como jurisprudencia"}
            </Button>
          )}
          {permisoObras.eliminar && r.es_propia && (
            <Button
              variant="ghost"
              size="sm"
              className="expedientes__accion--danger"
              type="button"
              onClick={() => onEliminar(r)}
              disabled={eliminandoId === r.id}
            >
              {eliminandoId === r.id ? "Eliminando..." : "Eliminar"}
            </Button>
          )}
        </div>
      ),
    },
  ];
}

// Tipos que no son un obrado del caso (espejo de categoria_fuente.py).
const TIPOS_NO_PROMOVIBLES = new Set([
  "doctrina",
  "criterio",
  "doctrina_libro",
  "material_caso",
  "jurisprudencia",
  "ejemplo",
]);

/** Un obrado publicado se puede promover si no lo está ya ni tiene propuesta pendiente. */
function puedePromover(r: ObraResumenDTO, esSupervisor: boolean): boolean {
  if (r.estado_visibilidad !== "publicado") return false;
  if (TIPOS_NO_PROMOVIBLES.has(r.tipo_documento)) return false;
  if (r.estado_validacion === "promovida") return false;
  // El operador solo propone lo propio y una vez; el supervisor promueve o aprueba.
  if (esSupervisor) return true;
  return r.es_propia && r.estado_validacion !== "promocion_pendiente";
}

/** Un obrado publicado se puede promover a norma una sola vez (propietario o supervisor). */
function puedePromoverANorma(
  r: ObraResumenDTO,
  esSupervisor: boolean,
): boolean {
  if (r.estado_visibilidad !== "publicado") return false;
  if (TIPOS_NO_PROMOVIBLES.has(r.tipo_documento)) return false;
  if (r.estado_validacion === "promovida_a_norma") return false;
  return esSupervisor || r.es_propia;
}

function badgeDoctrinaEstado(estado: string) {
  switch (estado) {
    case "privado":
      return <Badge tone="warning">Privada</Badge>;
    case "pendiente_aprobacion":
    case "pendiente":
      return <Badge tone="info">Pendiente aprobación</Badge>;
    case "global":
    case "publicado":
      return <Badge tone="success">Global</Badge>;
    case "rechazado":
      return <Badge tone="neutral">Rechazada</Badge>;
    default:
      return <Badge>{estado}</Badge>;
  }
}

function columnasDoctrina(
  onDescargar: (id: number) => void,
): DataTableColumn<DoctrinaDTO>[] {
  return [
    { key: "nombre_archivo", header: "Archivo" },
    {
      key: "autor",
      header: "Autor",
      render: (d) => d.autor || d.autor_instancia || "—",
    },
    {
      key: "procedencia",
      header: "Procedencia",
      render: (d) => d.procedencia || "—",
    },
    {
      key: "estado_visibilidad",
      header: "Estado",
      render: (d) => badgeDoctrinaEstado(d.estado_visibilidad),
    },
    {
      key: "_acciones",
      header: "Acciones",
      render: (d) => (
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => onDescargar(d.id)}
        >
          Descargar
        </Button>
      ),
    },
  ];
}
