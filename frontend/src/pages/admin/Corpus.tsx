// Admin Corpus: gestión del corpus jurídico. Visible solo para admin.
//
// 3 tabs:
//  - Normas:   listado + reconciliación Qdrant (Regla 3, con ConfirmDialog).
//  - Indexar:  carga de documentos + detección de patrones (F1.4) +
//              selector de endpoint de embedding (F1 multi-proveedor).
//  - Segmentos: navegación de fragmentos indexados (tab generado con DataTable).
//
// HU-04 (listar), HU-05/06/07 (indexar), Regla 3 (reconciliar), F1.4.
// Sin Redux/React Query (YAGNI): estado local.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type AjusteParametrosDTO,
  type ConfiguracionRAGDTO,
  type DeteccionPatronesDTO,
  type EndpointEmbeddingDTO,
  type EndpointModeloDTO,
  type FragmentoDTO,
  type NormaDTO,
  type OrdenNormas,
  type PaginaFragmentosDTO,
  ajustarParametrosRAG,
  detectarPatrones,
  editarNorma,
  eliminarNorma,
  indexarNorma,
  listarEndpointsEmbedding,
  listarEndpointsLLM,
  listarEndpointsReranker,
  listarFragmentos,
  listarNormas,
  obtenerConfiguracionRAG,
  obtenerLLMSeleccionado,
  obtenerNormalizarQuery,
  obtenerRerankerSeleccionado,
  reconciliarCorpus,
  seleccionarLLM,
  seleccionarReranker,
  setNormalizarQuery,
} from "../../api/corpus";

import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import {
  PageHeader,
  Button,
  Modal,
  Badge,
  SelectorModal,
  StateMessage,
  Tabs,
} from "../../components/ui";
import type { EstadoTrabajo } from "../../api/jobs";
import { useTrabajoIndexado } from "../../utils/useTrabajoIndexado";

import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import "./Corpus.css";

const ABREVIATURAS = [
  "CPE",
  "CPPM",
  "CPM",
  "LOJM",
  "LOFA",
  "CP",
  "CPP",
] as const;

type Tab = "normas" | "indexar" | "segmentos" | "modelos";

export default function Corpus() {
  const [tab, setTab] = useState<Tab>("normas");

  return (
    <div className="corpus-page">
      <PageHeader
        title="Corpus jurídico"
        subtitle="Normas, indexación y segmentos del corpus."
      />
      <Tabs<Tab>
        ariaLabel="Secciones del corpus"
        value={tab}
        onChange={setTab}
        items={[
          { value: "normas", label: "Normas" },
          { value: "indexar", label: "Indexar" },
          { value: "segmentos", label: "Segmentos" },
          { value: "modelos", label: "Modelos" },
        ]}
      />

      {tab === "normas" && <NormasTab />}
      {tab === "indexar" && <IndexarTab />}
      {tab === "segmentos" && <SegmentosTab />}
      {tab === "modelos" && <ModelosTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Modelos (LLM + reranker seleccionables por admin)
// ---------------------------------------------------------------------------

// Definicion de los umbrales ajustables (HU-23): label + rango + step.
const PARAMETROS_RAG: {
  clave: keyof AjusteParametrosDTO;
  label: string;
  min: number;
  max: number;
  step: number;
}[] = [
  {
    clave: "score_threshold",
    label: "Score mínimo de aceptación",
    min: 0,
    max: 1,
    step: 0.01,
  },
  {
    clave: "top_k_denso",
    label: "Candidatos densos",
    min: 1,
    max: 200,
    step: 1,
  },
  {
    clave: "top_k_lexico",
    label: "Candidatos léxicos (BM25)",
    min: 1,
    max: 200,
    step: 1,
  },
  {
    clave: "top_k_final",
    label: "Fragmentos finales tras reranking",
    min: 1,
    max: 100,
    step: 1,
  },
  {
    clave: "max_profundidad_bfs",
    label: "Profundidad de expansión jerárquica",
    min: 1,
    max: 10,
    step: 1,
  },
  {
    clave: "top_k_padres_a_incluir",
    label: "Nodos padre inyectados en el contexto",
    min: 0,
    max: 50,
    step: 1,
  },
  {
    clave: "temperatura",
    label: "Temperatura del LLM",
    min: 0,
    max: 1.5,
    step: 0.05,
  },
];

function ModelosTab() {
  const [llmEndpoints, setLlmEndpoints] = useState<EndpointModeloDTO[] | null>(
    null,
  );
  const [llmActivo, setLlmActivo] = useState<string>("");
  const [rerankerEndpoints, setRerankerEndpoints] = useState<
    EndpointModeloDTO[] | null
  >(null);
  const [rerankerActivo, setRerankerActivo] = useState<string>("");
  const [guardando, setGuardando] = useState<string | null>(null);
  const [normalizarQuery, setNormalizarQueryState] = useState<boolean>(true);
  const [parametros, setParametros] = useState<ConfiguracionRAGDTO | null>(
    null,
  );

  const cargar = useCallback(async () => {
    const [llmEps, rerankEps, llmSel, rerankSel, normQ, config] =
      await Promise.all([
        listarEndpointsLLM().catch(() => []),
        listarEndpointsReranker().catch(() => []),
        obtenerLLMSeleccionado().catch(() => null),
        obtenerRerankerSeleccionado().catch(() => null),
        obtenerNormalizarQuery().catch(() => null),
        obtenerConfiguracionRAG().catch(() => null),
      ]);
    setLlmEndpoints(llmEps);
    setRerankerEndpoints(rerankEps);
    setLlmActivo(llmSel?.id ?? llmEps[0]?.id ?? "");
    setRerankerActivo(rerankSel?.id ?? rerankEps[0]?.id ?? "");
    if (normQ !== null && normQ !== undefined) {
      setNormalizarQueryState(normQ.activado);
    }
    if (config !== null) {
      setParametros(config);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function guardarLLM() {
    setGuardando("llm");
    try {
      const sel = await seleccionarLLM(llmActivo || null);
      setLlmActivo(sel.id);
      toast(`LLM activo: ${sel.model}`, "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo actualizar el LLM."), "error");
    } finally {
      setGuardando(null);
    }
  }

  async function guardarReranker() {
    setGuardando("reranker");
    try {
      const sel = await seleccionarReranker(rerankerActivo || null);
      setRerankerActivo(sel.id);
      toast(`Reranker activo: ${sel.model}`, "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo actualizar el reranker."), "error");
    } finally {
      setGuardando(null);
    }
  }

  async function toggleNormalizarQuery(activado: boolean) {
    setGuardando("normalizar");
    try {
      await setNormalizarQuery(activado);
      setNormalizarQueryState(activado);
      toast(
        activado
          ? "Normalización de consultas activada."
          : "Normalización de consultas desactivada.",
        "success",
      );
    } catch (err) {
      toast(
        mensajeError(err, "No se pudo actualizar la normalización."),
        "error",
      );
    } finally {
      setGuardando(null);
    }
  }

  async function guardarParametros() {
    if (parametros === null) return;
    const valores = Object.fromEntries(
      PARAMETROS_RAG.map((p) => [p.clave, Number(parametros[p.clave])]),
    ) as AjusteParametrosDTO;
    setGuardando("parametros");
    try {
      const cfg = await ajustarParametrosRAG(valores);
      setParametros(cfg);
      toast("Parámetros del pipeline actualizados.", "success");
    } catch (err) {
      toast(
        mensajeError(err, "No se pudieron actualizar los parámetros."),
        "error",
      );
    } finally {
      setGuardando(null);
    }
  }

  return (
    <section className="corpus-page__modelos">
      <h2 className="corpus-page__upload-form-title">
        Modelos del pipeline RAG
      </h2>

      <div className="corpus-page__field">
        <label className="corpus-page__select-wrap">
          Modelo de LLM (generación de respuestas)
          {llmEndpoints === null ? (
            <input className="input" value="Cargando..." disabled readOnly />
          ) : llmEndpoints.length === 0 ? (
            <input
              className="input"
              value="Sin endpoints LLM configurados"
              disabled
              readOnly
            />
          ) : (
            <select
              className="select"
              value={llmActivo}
              onChange={(e) => setLlmActivo(e.target.value)}
            >
              {llmEndpoints.map((ep) => (
                <option key={ep.id} value={ep.id}>
                  {ep.model} ({ep.provider})
                </option>
              ))}
            </select>
          )}
        </label>
        <Button
          type="button"
          onClick={() => void guardarLLM()}
          disabled={guardando === "llm" || llmEndpoints === null}
        >
          {guardando === "llm" ? "Guardando..." : "Aplicar LLM"}
        </Button>
      </div>

      <div className="corpus-page__field">
        <label className="corpus-page__select-wrap">
          Modelo de reranker (reordenación por relevancia)
          {rerankerEndpoints === null ? (
            <input className="input" value="Cargando..." disabled readOnly />
          ) : rerankerEndpoints.length === 0 ? (
            <input
              className="input"
              value="Sin endpoints de reranker configurados"
              disabled
              readOnly
            />
          ) : (
            <select
              className="select"
              value={rerankerActivo}
              onChange={(e) => setRerankerActivo(e.target.value)}
            >
              {rerankerEndpoints.map((ep) => (
                <option key={ep.id} value={ep.id}>
                  {ep.model} ({ep.provider})
                </option>
              ))}
            </select>
          )}
        </label>
        <Button
          type="button"
          onClick={() => void guardarReranker()}
          disabled={guardando === "reranker" || rerankerEndpoints === null}
        >
          {guardando === "reranker" ? "Guardando..." : "Aplicar reranker"}
        </Button>
      </div>

      <div className="corpus-page__field">
        <label className="corpus-page__toggle">
          <input
            type="checkbox"
            checked={normalizarQuery}
            onChange={(e) => void toggleNormalizarQuery(e.target.checked)}
            disabled={guardando === "normalizar"}
          />
          Mejorar búsqueda (limpiar saludos y corregir errores de tipeo de la
          consulta)
        </label>
        <p className="corpus-page__hint">
          Al activar, el sistema limpia el prefijo ruidoso y corrige typos (por
          similitud con el corpus) antes de buscar. Desactívelo si prefieres
          usar la consulta tal cual.
        </p>
      </div>

      {parametros !== null && (
        <>
          <h2 className="corpus-page__upload-form-title">
            Parámetros del pipeline RAG
          </h2>
          {PARAMETROS_RAG.map((p) => (
            <div className="corpus-page__field" key={p.clave}>
              <label className="corpus-page__select-wrap">
                {p.label}
                <input
                  className="input"
                  type="number"
                  min={p.min}
                  max={p.max}
                  step={p.step}
                  value={String(parametros[p.clave])}
                  onChange={(e) =>
                    setParametros({
                      ...parametros,
                      [p.clave]: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
          ))}
          <Button
            type="button"
            onClick={() => void guardarParametros()}
            disabled={guardando === "parametros"}
          >
            {guardando === "parametros" ? "Guardando..." : "Aplicar parámetros"}
          </Button>
          <p className="corpus-page__hint">
            Los cambios aplican a las próximas consultas, sin reiniciar el
            servicio. Cada ajuste queda registrado en la auditoría.
          </p>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Tab: Normas (listado + reconciliación)
// ---------------------------------------------------------------------------

function NormasTab() {
  const [normas, setNormas] = useState<NormaDTO[] | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [editando, setEditando] = useState<NormaDTO | null>(null);
  const [editForm, setEditForm] = useState({ nombre: "", version: "" });
  const [savingEdit, setSavingEdit] = useState(false);
  const [porEliminar, setPorEliminar] = useState<NormaDTO | null>(null);
  const [eliminando, setEliminando] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");
  const [orden, setOrden] = useState<OrdenNormas>("abreviatura");

  const cargar = useCallback(async () => {
    try {
      setNormas(await listarNormas(orden));
    } catch {
      toast("No se pudo cargar el corpus.", "error");
    }
  }, [orden]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function reconciliar() {
    setReconciling(true);
    try {
      const r = await reconciliarCorpus();
      toast(
        `Sincronización: ${r.pg_count} documentos, ${r.qdrant_count} en el índice (Qdrant), ${r.huerfanos_eliminados} entradas sueltas eliminadas.`,
        "success",
      );
      setConfirmOpen(false);
      await cargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo sincronizar el índice."), "error");
      setConfirmOpen(false);
    } finally {
      setReconciling(false);
    }
  }

  const visibles = useMemo(() => {
    if (normas === null) return null;
    const q = busqueda.trim().toLowerCase();
    return normas.filter((n) => {
      if (filtroEstado === "indexado" && !n.indexado) return false;
      if (filtroEstado === "pendiente" && n.indexado) return false;
      if (q && !`${n.abreviatura} ${n.nombre}`.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [normas, busqueda, filtroEstado]);

  function startEdit(n: NormaDTO) {
    setEditando(n);
    setEditForm({ nombre: n.nombre, version: n.version ?? "" });
  }

  async function submitEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editando) return;
    setSavingEdit(true);
    try {
      await editarNorma(editando.norma_id, {
        nombre: editForm.nombre,
        version: editForm.version || undefined,
      });
      toast("Norma actualizada correctamente.", "success");
      setEditando(null);
      await cargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo editar la norma."), "error");
    } finally {
      setSavingEdit(false);
    }
  }

  async function confirmarEliminar() {
    if (porEliminar === null) return;
    setEliminando(true);
    try {
      await eliminarNorma(porEliminar.norma_id);
      toast("Norma eliminada.", "success");
      setPorEliminar(null);
      await cargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo eliminar la norma."), "error");
    } finally {
      setEliminando(false);
    }
  }

  const columnas: DataTableColumn<NormaDTO>[] = [
    {
      key: "abreviatura",
      header: "Abreviatura",
      render: (n) => (
        <span className="corpus-page__norma-card__abrev">{n.abreviatura}</span>
      ),
    },
    { key: "nombre", header: "Norma" },
    {
      key: "estado",
      header: "Estado",
      render: (n) => (
        <Badge tone={n.indexado ? "success" : "warning"}>
          {n.indexado ? "indexado" : "pendiente"}
        </Badge>
      ),
    },
    {
      key: "acciones",
      header: "",
      render: (n) => (
        <div className="corpus-page__acciones">
          <Button size="sm" variant="secondary" onClick={() => startEdit(n)}>
            Editar
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => setPorEliminar(n)}
            aria-label={`Eliminar ${n.abreviatura}`}
          >
            Eliminar
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <section className="corpus-page__normas">
        <div className="corpus-page__header">
          <h2>Normas del corpus</h2>
          <Button
            variant="secondary"
            onClick={() => setConfirmOpen(true)}
            disabled={reconciling}
          >
            Sincronizar índice de búsqueda
          </Button>
        </div>

        <DataTable<NormaDTO>
          columns={columnas}
          rowKey={(n) => n.norma_id}
          rows={visibles}
          searchPlaceholder="Buscar por abreviatura o nombre..."
          searchValue={busqueda}
          onSearchChange={setBusqueda}
          emptyMessage="Todavía no hay normas indexadas."
          filtros={
            <>
              <select
                className="select"
                value={orden}
                onChange={(e) => setOrden(e.target.value as OrdenNormas)}
                aria-label="Ordenar por"
              >
                <option value="abreviatura">Orden: abreviatura</option>
                <option value="nombre">Orden: nombre</option>
                <option value="tipo">Orden: tipo</option>
                <option value="jerarquia">Orden: jerarquía</option>
                <option value="indexado">Orden: estado</option>
              </select>
              <select
                className="select"
                value={filtroEstado}
                onChange={(e) => setFiltroEstado(e.target.value)}
                aria-label="Filtrar por estado"
              >
                <option value="">Todos los estados</option>
                <option value="indexado">Indexadas</option>
                <option value="pendiente">Pendientes</option>
              </select>
            </>
          }
        />
      </section>

      {editando !== null && (
        <Modal
          open
          title={`Editar norma: ${editando.abreviatura}`}
          onClose={() => setEditando(null)}
          busy={savingEdit}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setEditando(null)}
                disabled={savingEdit}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                form="corpus-edit-form"
                loading={savingEdit}
              >
                Guardar cambios
              </Button>
            </>
          }
        >
          <form id="corpus-edit-form" onSubmit={submitEdit}>
            <div className="corpus-page__field">
              <label className="corpus-page__select-wrap">
                Nombre completo
                <input
                  className="input"
                  value={editForm.nombre}
                  onChange={(e) =>
                    setEditForm({ ...editForm, nombre: e.target.value })
                  }
                  required
                />
              </label>
              <label className="corpus-page__select-wrap">
                Versión
                <input
                  className="input"
                  value={editForm.version}
                  onChange={(e) =>
                    setEditForm({ ...editForm, version: e.target.value })
                  }
                  placeholder="2024"
                />
              </label>
            </div>
          </form>
        </Modal>
      )}

      <ConfirmDialog
        open={porEliminar !== null}
        title="Eliminar norma"
        danger
        confirmLabel="Eliminar"
        message={
          <>
            La norma <strong>{porEliminar?.abreviatura}</strong> dejará de
            aparecer en el corpus. Los fragmentos ya indexados se conservan en
            Qdrant por trazabilidad (no se borran vectores). ¿Continuar?
          </>
        }
        busy={eliminando}
        onCancel={() => setPorEliminar(null)}
        onConfirm={() => void confirmarEliminar()}
      />

      <ConfirmDialog
        open={confirmOpen}
        title="Sincronizar índice de búsqueda"
        danger
        confirmLabel="Sincronizar"
        message={
          <>
            Se compararán los documentos guardados con el índice de búsqueda
            (Qdrant). Las entradas del índice que ya no tienen documento se{" "}
            <strong>eliminarán</strong>. ¿Continuar?
          </>
        }
        busy={reconciling}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => void reconciliar()}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Indexar (upload + detección + selector de embedding)
// ---------------------------------------------------------------------------

function IndexarTab() {
  const [abreviatura, setAbreviatura] = useState<string>("");
  const [version, setVersion] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [endpoints, setEndpoints] = useState<EndpointEmbeddingDTO[] | null>(
    null,
  );
  const [endpointId, setEndpointId] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [progreso, setProgreso] = useState(0);
  const [errorSubida, setErrorSubida] = useState<string | null>(null);
  const [deteccion, setDeteccion] = useState<DeteccionPatronesDTO | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trabajo = useTrabajoIndexado();

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const eps = await listarEndpointsEmbedding();
        if (!alive) return;
        setEndpoints(eps);
        setEndpointId(eps[0]?.id ?? "");
      } catch {
        if (alive) setEndpoints([]);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  function handlePick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setDeteccion(null);
    if (!f) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void detectarPatrones(f)
        .then((d) => {
          setDeteccion(d);
          if (d.mejor) setAbreviatura(d.mejor);
        })
        .catch(() => {
          setDeteccion({
            mejor: null,
            confianza: 0,
            candidatos: [],
            error: "No se pudo detectar el patrón.",
          });
        });
    }, 300);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !abreviatura) {
      toast("Seleccioná archivo y abreviatura.", "warning");
      return;
    }
    setUploading(true);
    setProgreso(0);
    setErrorSubida(null);
    try {
      const encolado = await indexarNorma(
        abreviatura,
        file,
        version || undefined,
        endpointId || undefined,
        setProgreso,
      );
      setUploading(false);

      const final = await trabajo.seguir(
        encolado.job_id,
        encolado.estado as EstadoTrabajo,
      );
      if (final === null) return; // desmontado mientras seguía el trabajo
      if (final.estado === "completado") {
        const r = final.resultado ?? {};
        const fragmentos =
          typeof r.fragmentos_creados === "number" ? r.fragmentos_creados : "?";
        const vectores =
          typeof r.vectores_indexados === "number" ? r.vectores_indexados : "?";
        const coleccion =
          typeof r.qdrant_collection === "string"
            ? r.qdrant_collection
            : "corpus_juridico";
        toast(
          `Indexado: ${fragmentos} fragmentos, ${vectores} vectores (${coleccion}).`,
          "success",
        );
        setFile(null);
        if (inputRef.current) inputRef.current.value = "";
      } else if (final.estado === "cancelado") {
        toast("Indexado cancelado.", "info");
      } else {
        const msg = final.error ?? "No se pudo indexar la norma.";
        setErrorSubida(msg);
        toast(msg, "error");
      }
    } catch (err) {
      const msg = mensajeError(err, "No se pudo indexar la norma.");
      setErrorSubida(msg);
      toast(msg, "error");
    } finally {
      setUploading(false);
    }
  }

  async function cancelarIndexado() {
    try {
      await trabajo.cancelar();
      toast("Cancelando el indexado…", "info");
    } catch (err) {
      toast(mensajeError(err, "No se pudo cancelar el indexado."), "error");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="corpus-page__upload-form">
      <h2 className="corpus-page__upload-form-title">Indexar norma</h2>
      <div className="corpus-page__field">
        <label className="corpus-page__select-wrap">
          Abreviatura
          <select
            className="select"
            value={abreviatura}
            onChange={(e) => setAbreviatura(e.target.value)}
          >
            <option value="" disabled>
              Seleccioná la fuente...
            </option>
            {ABREVIATURAS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="corpus-page__select-wrap">
          Versión (opcional)
          <input
            className="input"
            type="text"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="2024"
          />
        </label>
        <label className="corpus-page__select-wrap">
          Modelo de embedding
          {endpoints === null ? (
            <input className="input" value="Cargando..." disabled readOnly />
          ) : endpoints.length === 0 ? (
            <input
              className="input"
              value="Sin endpoints configurados"
              disabled
              readOnly
            />
          ) : (
            <select
              className="select"
              value={endpointId}
              onChange={(e) => setEndpointId(e.target.value)}
            >
              {endpoints.map((ep) => (
                <option key={ep.id} value={ep.id}>
                  {ep.model} ({ep.provider}, {ep.dim} dims)
                </option>
              ))}
            </select>
          )}
        </label>
        <label className="corpus-page__file-input">
          PDF / DOCX
          <input
            ref={inputRef}
            className="input"
            type="file"
            accept=".pdf,.docx"
            onChange={handlePick}
          />
        </label>
      </div>

      {deteccion !== null && (
        <PanelDeteccion deteccion={deteccion} abreviatura={abreviatura} />
      )}

      <div className="corpus-page__field">
        {trabajo.enCurso && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => void cancelarIndexado()}
            disabled={trabajo.cancelando}
          >
            {trabajo.cancelando ? "Cancelando…" : "Cancelar indexado"}
          </Button>
        )}
        <Button
          type="submit"
          disabled={uploading || trabajo.enCurso}
          aria-busy={uploading || trabajo.enCurso}
        >
          {uploading
            ? progreso < 100
              ? `Subiendo ${progreso}%`
              : "Encolando…"
            : trabajo.enCurso
              ? "Indexando…"
              : "Subir e indexar"}
        </Button>
        {(uploading || trabajo.enCurso) && (
          <div className="corpus-page__progress" />
        )}
      </div>
      {trabajo.enCurso && (
        <p className="corpus-page__hint">
          Indexando: podés cancelarlo, y se detiene al terminar la fase en
          curso.
        </p>
      )}
      {errorSubida && <StateMessage tipo="error">{errorSubida}</StateMessage>}
    </form>
  );
}

function PanelDeteccion({
  deteccion,
  abreviatura,
}: {
  deteccion: DeteccionPatronesDTO;
  abreviatura: string;
}) {
  if (deteccion.error !== null) {
    return (
      <div className="corpus-page__deteccion">
        <p className="corpus-page__deteccion__msg">{deteccion.error}</p>
      </div>
    );
  }
  const mejor = deteccion.mejor;
  const coincide = mejor !== null && abreviatura === mejor;
  return (
    <div
      className={
        "corpus-page__deteccion" +
        (coincide
          ? " corpus-page__deteccion--match"
          : " corpus-page__deteccion--mismatch")
      }
    >
      <p className="corpus-page__deteccion__titulo">
        Patrón detectado: <strong>{mejor ?? "—"}</strong>
        {mejor !== null && (
          <span className="corpus-page__deteccion__confianza">
            {" "}
            (confianza {Math.round((deteccion.confianza ?? 0) * 100)}%)
          </span>
        )}
      </p>
      {deteccion.candidatos.map((c) => (
        <div key={c.abreviatura} className="corpus-page__deteccion__candidato">
          <span>{c.abreviatura}</span>
          <span>{c.articulos_matcheados} art.</span>
          <span>{Math.round(c.confianza * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Segmentos (navegación de fragmentos indexados)
// ---------------------------------------------------------------------------

const POR_PAGINA = 10;

function fragmentosColumns(
  normas: NormaDTO[],
): DataTableColumn<FragmentoDTO>[] {
  const abrev = (id: number | null): string => {
    const n = normas.find((x) => x.norma_id === id);
    return n ? n.abreviatura : String(id ?? "—");
  };
  return [
    {
      key: "norma_id",
      header: "Norma",
      render: (f) => abrev(f.norma_id),
    },
    { key: "tipo_chunk", header: "Tipo" },
    {
      key: "texto",
      header: "Texto",
      render: (f) => <span className="corpus-page__frag-texto">{f.texto}</span>,
    },
    { key: "nivel_jerarquico", header: "Nivel" },
    {
      key: "padre",
      header: "Padre",
      render: (f) => (f.padre_ref_key ? <code>{f.padre_ref_key}</code> : "—"),
    },
  ];
}

function SegmentosTab() {
  const [pagina, setPagina] = useState(1);
  const [texto, setTexto] = useState("");
  const [normaId, setNormaId] = useState("");
  const [tipoChunk, setTipoChunk] = useState("");
  const [normas, setNormas] = useState<NormaDTO[]>([]);
  const [selectorNorma, setSelectorNorma] = useState(false);
  const [data, setData] = useState<PaginaFragmentosDTO | null>(null);
  const queryKeyRef = useRef("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const ns = await listarNormas();
        if (alive) setNormas(ns);
      } catch {
        /* listado informativo */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const queryKey = `${pagina}|${normaId}|${tipoChunk}|${texto.trim()}`;

  useEffect(() => {
    const key = queryKey;
    queryKeyRef.current = key;
    let alive = true;
    (async () => {
      setData(null);
      try {
        const res = await listarFragmentos({
          pagina,
          por_pagina: POR_PAGINA,
          norma_id: normaId ? Number(normaId) : undefined,
          tipo_chunk: tipoChunk || undefined,
          texto: texto.trim() || undefined,
        });
        if (alive && queryKeyRef.current === key) setData(res);
      } catch {
        if (alive && queryKeyRef.current === key) {
          toast("No se pudieron cargar los segmentos.", "error");
          setData({ items: [], total: 0, pagina, por_pagina: POR_PAGINA });
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [queryKey, pagina, normaId, tipoChunk, texto]);

  return (
    <section className="corpus-page__segmentos">
      <SelectorModal
        open={selectorNorma}
        title="Filtrar por norma"
        opciones={[
          { id: "", titulo: "Todas las normas" },
          ...normas.map((n) => ({
            id: String(n.norma_id),
            titulo: n.abreviatura,
            detalle: n.nombre,
          })),
        ]}
        placeholder="Buscar por abreviatura o nombre"
        seleccionado={normaId}
        onSeleccionar={(id) => {
          setNormaId(id);
          setPagina(1);
          setSelectorNorma(false);
        }}
        onClose={() => setSelectorNorma(false)}
      />
      <h2 className="corpus-page__upload-form-title">Segmentos indexados</h2>
      <DataTable<FragmentoDTO>
        numerada
        columns={fragmentosColumns(normas)}
        rowKey={(r) => r.id}
        rows={data?.items ?? null}
        total={data?.total ?? null}
        page={pagina}
        pageSize={POR_PAGINA}
        onPageChange={setPagina}
        searchPlaceholder="Buscar texto..."
        searchValue={texto}
        onSearchChange={(v) => {
          setTexto(v);
          setPagina(1);
        }}
        emptyMessage={"No hay segmentos. Subí una norma en el tab Indexar."}
        filtros={
          <>
            <div className="corpus-page__select-wrap">
              <span id="corpus-filtro-norma">Norma</span>
              <Button
                variant="secondary"
                aria-haspopup="dialog"
                aria-describedby="corpus-filtro-norma"
                onClick={() => setSelectorNorma(true)}
              >
                {normas.find((n) => String(n.norma_id) === normaId)
                  ?.abreviatura ?? "Todas"}
              </Button>
            </div>
            <label className="corpus-page__select-wrap">
              Tipo
              <select
                className="select"
                value={tipoChunk}
                onChange={(e) => {
                  setTipoChunk(e.target.value);
                  setPagina(1);
                }}
                aria-label="Filtrar por tipo"
              >
                <option value="">Todos</option>
                <option value="articulo_simple">Artículo simple</option>
                <option value="articulo_compuesto">Artículo compuesto</option>
                <option value="seccion">Sección</option>
                <option value="inciso_compuesto">Inciso</option>
              </select>
            </label>
          </>
        }
      />
    </section>
  );
}
