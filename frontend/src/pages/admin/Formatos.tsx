// Admin Formatos: gestión de layouts de obrados TSJM.
//
// Modo principal (todos): vista documento-like (hoja) + edición tipo Word.
// Modo Bloques (solo administrador): lista técnica de bloques editable.
// PATCH /admin/formatos/{id}/bloques/pN:iM persiste cada corrección.

import { useCallback, useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";

import {
  type BloqueDTO,
  type BloqueEsqueletoDTO,
  type FormatoDTO,
  actualizarBloque,
  actualizarConfiguracion,
  eliminarBloqueApi,
  listarFormatos,
  obtenerDocxOriginal,
  obtenerFormato,
  promoverFormato,
  reordenarBloques,
} from "../../api/formatos";
import { useAuth } from "../../context/useAuth";
import { usePermisos } from "../../context/usePermisos";
import { PageHeader, Button, Modal } from "../../components/ui";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import DocumentoPreview, {
  type MargenesMM,
  type PreviewOverride,
  type TamanoHoja,
} from "./DocumentoPreview";
import type { Snapshot } from "./Snapshot";
import FormatoEditor, { type CambioBloque } from "./FormatoEditor";

import "./Formatos.css";

const TIPOS = [
  "auto_vista",
  "proyecto_auto_vista",
  "dictamen_radicatoria",
  "dictamen_fondo",
  "relacion_obrados",
  "acta_audiencia",
  "sentencia",
  "auto_interlocutorio",
  "otro",
] as const;

export default function Formatos() {
  const { auth } = useAuth();
  const esAdmin = auth.rol === "administrador";
  const puedeActualizar = usePermisos().puede("formatos", "actualizar");

  const [filtros, setFiltros] = useState({ tipo: "", autor: "", estado: "" });
  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<{
    items: FormatoDTO[];
    total: number;
  } | null>(null);
  const [selected, setSelected] = useState<FormatoDTO | null>(null);
  const [tamano, setTamano] = useState<TamanoHoja>("carta");
  const [modo, setModo] = useState<"word" | "bloques">("word");
  const [editando, setEditando] = useState<{
    key: string;
    texto: string;
    align: string;
    bold: boolean;
    underline: boolean;
    size_pt: number | null;
    font: string | null;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [comparadorActivo, setComparadorActivo] = useState(false);
  const [docxInlineCargado, setDocxInlineCargado] = useState(false);
  const [margenes, setMargenes] = useState<MargenesMM>({
    top: 25,
    right: 20,
    bottom: 20,
    left: 40,
  });
  const [margenesManual, setMargenesManual] = useState<MargenesMM | null>(null);
  const [overrides, setOverrides] = useState<Record<string, PreviewOverride>>(
    {},
  );
  const [ordenLocal, setOrdenLocal] = useState<string[] | null>(null);
  const [aEliminar, setAEliminar] = useState<Set<string>>(new Set());
  // Historial para Undo/Redo de cambios locales (overrides/orden/eliminación).
  const [pasado, setPasado] = useState<Snapshot[]>([]);
  const [futuro, setFuturo] = useState<Snapshot[]>([]);
  const docxInlineRef = useRef<HTMLDivElement | null>(null);

  async function toggleComparador() {
    if (!selected) return;
    const next = !comparadorActivo;
    setComparadorActivo(next);
    if (next) {
      setDocxInlineCargado(false);
      const blob = await obtenerDocxOriginal(selected.id);
      // esperar a que el ref inline esté montado
      requestAnimationFrame(async () => {
        if (blob && docxInlineRef.current) {
          docxInlineRef.current.innerHTML = "";
          await renderAsync(blob, docxInlineRef.current);
          setDocxInlineCargado(true);
        }
      });
    }
  }

  // Snapshot actual del estado local (para Undo/Redo).
  const snapshotActual = useCallback(
    (): Snapshot => ({
      overrides,
      ordenLocal,
      aEliminar: [...aEliminar],
    }),
    [overrides, ordenLocal, aEliminar],
  );

  // Registrar un cambio local: empuja snapshot al pasado y limpia el futuro.
  const registrarCambio = useCallback(() => {
    setPasado((p) => [...p, snapshotActual()]);
    setFuturo([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotActual]);

  // Deshacer: volver al estado local anterior.
  const deshacer = useCallback(() => {
    setPasado((p) => {
      if (p.length === 0) return p;
      const prev = p[p.length - 1];
      setFuturo((f) => [...f, snapshotActual()]);
      setOverrides(prev.overrides);
      setOrdenLocal(prev.ordenLocal);
      setAEliminar(new Set(prev.aEliminar));
      setEditando(null);
      return p.slice(0, -1);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotActual]);

  // Rehacer: reaplicar el estado local que se deshizo.
  const rehacer = useCallback(() => {
    setFuturo((f) => {
      if (f.length === 0) return f;
      const next = f[f.length - 1];
      setPasado((p) => [...p, snapshotActual()]);
      setOverrides(next.overrides);
      setOrdenLocal(next.ordenLocal);
      setAEliminar(new Set(next.aEliminar));
      setEditando(null);
      return f.slice(0, -1);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotActual]);

  // Cancelar: descartar todos los cambios locales (sin tocar BD).
  const cancelarLocal = useCallback(() => {
    setOverrides({});
    setOrdenLocal(null);
    setAEliminar(new Set());
    setPasado([]);
    setFuturo([]);
    setEditando(null);
  }, []);

  // Cuando cambia el formato seleccionado, reset comparador y overrides
  useEffect(() => {
    setComparadorActivo(false);
    setDocxInlineCargado(false);
    setOverrides({});
    setEditando(null);
    setOrdenLocal(null);
    setAEliminar(new Set());
    setPasado([]);
    setFuturo([]);
  }, [selected?.id]);

  const cargar = useCallback(async () => {
    try {
      const res = await listarFormatos({
        tipo_documento: filtros.tipo || undefined,
        autor: filtros.autor || undefined,
        estado: filtros.estado || undefined,
        pagina,
        por_pagina: 10,
      });
      setData({ items: res.items, total: res.total });
    } catch (err) {
      toast(mensajeError(err, "No se pudieron cargar los formatos."), "error");
    }
  }, [filtros, pagina]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function abrirDetalle(id: number) {
    try {
      const f = await obtenerFormato(id);
      setSelected(f);
      setModo("word");
      setEditando(null);
      // Inicializar config global desde meta.page si existe.
      const page = (f.meta?.page ?? {}) as Record<string, unknown>;
      if (
        page.tamano_hoja === "carta" ||
        page.tamano_hoja === "oficio" ||
        page.tamano_hoja === "a4"
      ) {
        setTamano(page.tamano_hoja);
      }
      setMargenes({
        top: Number(page.margin_top_mm ?? 25),
        right: Number(page.margin_right_mm ?? 20),
        bottom: Number(page.margin_bottom_mm ?? 20),
        left: Number(page.margin_left_mm ?? 40),
      });
    } catch (err) {
      toast(mensajeError(err, "No se pudo abrir el formato."), "error");
    }
  }

  function textoDeBloque(key: string): string {
    const ov = overrides[key]?.texto;
    if (ov !== undefined) return ov;
    if (!selected) return "";
    const esq = selected.esqueleto?.find(
      (b) => `p${b.page}:i${b.index}` === key,
    );
    if (esq?.texto_plantilla) return esq.texto_plantilla;
    const crudo = selected.bloques.find(
      (b) => `p${b.page}:i${b.index}` === key,
    );
    if (crudo) return crudo.runs.map((r) => r.text).join("");
    return "";
  }

  // Estilo del bloque para sembrar el editor inline fiel al actual.
  // Prioridad: override del bloque si existe, si no esqueleto/bloques.
  function estiloDeBloque(key: string) {
    const ov = overrides[key];
    if (ov) {
      // Si hay override, construir estilo fusionando: override gana sobre esqueleto.
      const base = (() => {
        if (!selected) return null;
        return (
          selected.esqueleto?.find((x) => `p${x.page}:i${x.index}` === key) ??
          selected.bloques.find((x) => `p${x.page}:i${x.index}` === key)
        );
      })();
      const r0 = base?.runs[0];
      return {
        align: ov.align ?? base?.align ?? "left",
        bold: ov.bold ?? r0?.bold ?? false,
        underline: ov.underline ?? r0?.underline ?? false,
        size_pt: ov.size_pt ?? r0?.size_pt ?? null,
        font: ov.font ?? r0?.font ?? null,
      };
    }
    if (!selected)
      return {
        align: "left",
        bold: false,
        underline: false,
        size_pt: null,
        font: null,
      };
    const b =
      selected.esqueleto?.find((x) => `p${x.page}:i${x.index}` === key) ??
      selected.bloques.find((x) => `p${x.page}:i${x.index}` === key);
    const r0 = b?.runs[0];
    return {
      align: b?.align ?? "left",
      bold: r0?.bold ?? false,
      underline: r0?.underline ?? false,
      size_pt: r0?.size_pt ?? null,
      font: r0?.font ?? null,
    };
  }

  async function handlePromover() {
    if (!selected) return;
    try {
      const f = await promoverFormato(selected.id);
      setSelected(f);
      toast(`Formato ${f.slug} promovido a canónico.`, "success");
      void cargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo promover."), "error");
    }
  }

  async function guardarBloque(key: string, cambio: CambioBloque) {
    if (!selected) return;
    setSaving(true);
    try {
      const f = await actualizarBloque(selected.id, key, {
        text: cambio.texto,
        align: cambio.align,
        bold: cambio.bold,
        underline: cambio.underline,
        size_pt: cambio.size_pt,
        font: cambio.font,
      });
      setSelected(f);
      setOverrides((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setEditando(null);
      toast("Bloque actualizado.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo guardar."), "error");
    } finally {
      setSaving(false);
    }
  }

  function handleCambio(key: string, cambio: CambioBloque) {
    const cur = overrides[key];
    const same =
      cur &&
      cur.texto === cambio.texto &&
      cur.align === cambio.align &&
      cur.bold === cambio.bold &&
      cur.underline === cambio.underline &&
      cur.size_pt === cambio.size_pt &&
      cur.font === cambio.font;
    if (!same) {
      setPasado((p) => [...p, snapshotActual()]);
      setFuturo([]);
    }
    setOverrides((prev) => ({
      ...prev,
      [key]: {
        texto: cambio.texto,
        align: cambio.align,
        bold: cambio.bold,
        underline: cambio.underline,
        size_pt: cambio.size_pt,
        font: cambio.font,
      },
    }));
  }

  // Aplicar estilo a una selección de bloques (toolbar flotante de selección).
  function aplicarSeleccion(claves: string[], cambio: PreviewOverride) {
    registrarCambio();
    setOverrides((prev) => {
      const n = { ...prev };
      for (const k of claves) {
        n[k] = { ...prev[k], ...cambio };
      }
      return n;
    });
  }

  // Guardar todo: persiste config, reorden, eliminaciones y overrides.
  async function guardarTodo() {
    if (!selected) return;
    const claves = Object.keys(overrides);
    const hayCambios =
      claves.length > 0 || ordenLocal !== null || aEliminar.size > 0;
    if (!hayCambios) {
      toast("No hay cambios pendientes.", "info");
      return;
    }
    setSaving(true);
    let ok = 0;
    try {
      // 1. Config global (tamaño de hoja + márgenes).
      await actualizarConfiguracion(selected.id, {
        tamano_hoja: tamano,
        margin_top_mm: margenes.top,
        margin_right_mm: margenes.right,
        margin_bottom_mm: margenes.bottom,
        margin_left_mm: margenes.left,
      });
      // 2. Reorden.
      if (ordenLocal) {
        await reordenarBloques(selected.id, ordenLocal);
        ok++;
      }
      // 3. Eliminaciones.
      for (const k of aEliminar) {
        await eliminarBloqueApi(selected.id, k);
        ok++;
      }
      // 4. Overrides por bloque.
      for (const k of claves) {
        const ov = overrides[k];
        await actualizarBloque(selected.id, k, {
          text: ov.texto,
          align: ov.align,
          bold: ov.bold,
          underline: ov.underline,
          size_pt: ov.size_pt,
          font: ov.font,
        });
        ok++;
      }
      const f = await obtenerFormato(selected.id);
      setSelected(f);
      setOverrides({});
      setOrdenLocal(null);
      setAEliminar(new Set());
      setPasado([]);
      setFuturo([]);
      setEditando(null);
      toast(`Guardado: ${ok} cambio${ok !== 1 ? "s" : ""}.`, "success");
      void cargar();
    } catch (err) {
      toast(mensajeError(err, `Se guardaron ${ok}, falló el resto.`), "error");
    } finally {
      setSaving(false);
    }
  }

  const columnas: DataTableColumn<FormatoDTO>[] = [
    { key: "slug", header: "Slug" },
    { key: "tipo_documento", header: "Tipo" },
    { key: "autor", header: "Autor" },
    {
      key: "estado",
      header: "Estado",
      render: (f) => (
        <span
          className={
            f.estado === "canonico"
              ? "formatos-badge--ok"
              : "formatos-badge--warn"
          }
        >
          {f.estado}
        </span>
      ),
    },
    {
      key: "acciones",
      header: "",
      render: (f) => (
        <Button variant="secondary" onClick={() => void abrirDetalle(f.id)}>
          Ver
        </Button>
      ),
    },
  ];

  // Bloques a renderizar en la vista: el esqueleto si existe, si no los crudos.
  // Eliminaciones pendientes se filtran aquí; el reorden se resuelve en
  // DocumentoPreview via prop `orden` para no duplicar lógica.
  const bloquesVista: Array<BloqueDTO | BloqueEsqueletoDTO> = (() => {
    const base =
      selected?.esqueleto && selected.esqueleto.length > 0
        ? selected.esqueleto
        : (selected?.bloques ?? []);
    return base.filter((b) => !aEliminar.has(`p${b.page}:i${b.index}`));
  })();

  return (
    <div className="formatos-page">
      <PageHeader
        title="Formatos TSJM"
        subtitle="Layouts de obrados — edición tipo Word y canónicos."
      />

      <div className="formatos-page__filtros">
        <select
          className="select"
          aria-label="Filtrar por tipo"
          value={filtros.tipo}
          onChange={(e) => {
            setFiltros({ ...filtros, tipo: e.target.value });
            setPagina(1);
          }}
        >
          <option value="">Todos los tipos</option>
          {TIPOS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          className="select"
          aria-label="Filtrar por autor"
          value={filtros.autor}
          onChange={(e) => {
            setFiltros({ ...filtros, autor: e.target.value });
            setPagina(1);
          }}
        >
          <option value="">Todos los autores</option>
          <option value="aliaga">aliaga</option>
          <option value="tsjm-otro">tsjm-otro</option>
          <option value="desconocido">desconocido</option>
        </select>
        <select
          className="select"
          aria-label="Filtrar por estado"
          value={filtros.estado}
          onChange={(e) => {
            setFiltros({ ...filtros, estado: e.target.value });
            setPagina(1);
          }}
        >
          <option value="">Todos los estados</option>
          <option value="borrador">borrador</option>
          <option value="canonico">canónico</option>
        </select>
      </div>

      <DataTable<FormatoDTO>
        columns={columnas}
        rowKey={(r) => r.id}
        rows={data?.items ?? null}
        total={data?.total ?? null}
        page={pagina}
        pageSize={10}
        onPageChange={setPagina}
        emptyMessage="Sin formatos. Importá desde el pipeline `tools/formatos`."
      />

      {selected && (
        <Modal
          open
          title={`${selected.slug} — v${selected.version}`}
          onClose={() => setSelected(null)}
          busy={saving}
          size="xl"
        >
          <div className="formatos-detalle__meta">
            <span>Tipo: {selected.tipo_documento}</span> ·{" "}
            <span>Autor: {selected.autor}</span> ·{" "}
            <span>Motor: {selected.engine}</span>
            {puedeActualizar && (
              <Button
                variant="secondary"
                onClick={() => void handlePromover()}
                disabled={selected.estado === "canonico"}
              >
                {selected.estado === "canonico"
                  ? "Canónico"
                  : "Promover a canónico"}
              </Button>
            )}
            {esAdmin && (
              <Button
                variant="ghost"
                onClick={() => setModo(modo === "word" ? "bloques" : "word")}
              >
                {modo === "word" ? "Modo bloques (admin)" : "Modo Word"}
              </Button>
            )}
          </div>

          {modo === "word" ? (
            <div className="formatos-word-layout">
              <DocumentoPreview
                bloques={bloquesVista}
                tamano={tamano}
                onTamanoChange={setTamano}
                mostrarComparador={selected.engine === "python-docx"}
                comparadorActivo={comparadorActivo}
                onToggleComparador={() => void toggleComparador()}
                overrides={overrides}
                margenes={margenes}
                onMargenesChange={(m) => setMargenes(m)}
                onAbrirMargenesManual={() => setMargenesManual(margenes)}
                onAplicarSeleccion={(claves, cambio) =>
                  aplicarSeleccion(claves, cambio)
                }
                orden={ordenLocal}
                onReordenar={(o) => {
                  registrarCambio();
                  setOrdenLocal(o);
                }}
                onDeshacer={deshacer}
                onRehacer={rehacer}
                canDeshacer={pasado.length > 0}
                canRehacer={futuro.length > 0}
                onCancelarLocal={cancelarLocal}
                onGuardarTodo={() => void guardarTodo()}
                hayCambios={
                  Object.keys(overrides).length > 0 ||
                  !!ordenLocal ||
                  aEliminar.size > 0
                }
                saving={saving}
                onEliminarSeleccion={(claves) => {
                  registrarCambio();
                  setAEliminar((prev) => new Set([...prev, ...claves]));
                  setOverrides((prev) => {
                    const n = { ...prev };
                    claves.forEach((k) => delete n[k]);
                    return n;
                  });
                  if (editando && claves.includes(editando.key))
                    setEditando(null);
                }}
                editandoKey={editando?.key ?? null}
                onEditarBloque={(key) =>
                  setEditando({
                    key,
                    texto: textoDeBloque(key),
                    ...estiloDeBloque(key),
                  })
                }
                onCerrarEdicion={() => setEditando(null)}
                puedeEditar={puedeActualizar}
                editorSlot={
                  editando ? (
                    <FormatoEditor
                      inicial={editando.texto}
                      estiloInicial={{
                        align: editando.align,
                        bold: editando.bold,
                        underline: editando.underline,
                        size_pt: editando.size_pt,
                        font: editando.font,
                      }}
                      onGuardar={(c) => void guardarBloque(editando.key, c)}
                      onCambio={(c) => handleCambio(editando.key, c)}
                      onCancelar={() => {
                        setOverrides((prev) => {
                          const n = { ...prev };
                          delete n[editando.key];
                          return n;
                        });
                        setEditando(null);
                      }}
                      disabled={saving}
                      puedeEditar={puedeActualizar}
                      modo="inline"
                    />
                  ) : undefined
                }
              />
              {comparadorActivo && (
                <div className="formato-docx-compare formato-docx-compare--inline">
                  <h4 className="formato-docx-compare__title">
                    .docx original — lado a lado
                  </h4>
                  {!docxInlineCargado && (
                    <p className="formato-docx-compare__loading">
                      Cargando documento original…
                    </p>
                  )}
                  <div
                    ref={docxInlineRef}
                    className="formato-docx-compare__docx"
                  />
                </div>
              )}
            </div>
          ) : (
            <ul className="formatos-detalle__bloques">
              {selected.bloques.map((b) => {
                const key = `p${b.page}:i${b.index}`;
                const texto = b.runs.map((r) => r.text).join(" ");
                return (
                  <li
                    key={key}
                    className={
                      "formatos-bloque" +
                      (b.review ? " formatos-bloque--review" : "")
                    }
                  >
                    <code>{key}</code> [{b.align}] {b.confidence.toFixed(2)}{" "}
                    {b.review ? "· revisar" : ""}{" "}
                    {b.overridden ? "· corregido" : ""}
                    <p>{texto.slice(0, 180)}</p>
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setEditando({
                          key,
                          texto: b.runs[0]?.text ?? texto,
                          ...estiloDeBloque(key),
                        })
                      }
                    >
                      Corregir
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}

          {editando && modo === "bloques" && (
            <div className="formatos-edit">
              <h4>Editar {editando.key}</h4>
              <FormatoEditor
                inicial={editando.texto}
                estiloInicial={{
                  align: editando.align,
                  bold: editando.bold,
                  underline: editando.underline,
                  size_pt: editando.size_pt,
                  font: editando.font,
                }}
                onGuardar={(c) => void guardarBloque(editando.key, c)}
                onCambio={(c) => handleCambio(editando.key, c)}
                onCancelar={() => {
                  setOverrides((prev) => {
                    const n = { ...prev };
                    delete n[editando.key];
                    return n;
                  });
                  setEditando(null);
                }}
                disabled={saving}
                puedeEditar={puedeActualizar}
              />
            </div>
          )}
        </Modal>
      )}

      {margenesManual && (
        <Modal
          open
          title="Márgenes (mm)"
          onClose={() => setMargenesManual(null)}
          size="sm"
        >
          <div className="formatos-margenes-manual">
            {(["top", "right", "bottom", "left"] as const).map((lado) => (
              <label key={lado}>
                {lado === "top"
                  ? "Superior"
                  : lado === "right"
                    ? "Derecho"
                    : lado === "bottom"
                      ? "Inferior"
                      : "Izquierdo"}
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={100}
                  value={margenesManual[lado]}
                  onChange={(e) =>
                    setMargenesManual({
                      ...margenesManual,
                      [lado]: Number(e.target.value) || 0,
                    })
                  }
                />
              </label>
            ))}
            <div className="formatos-margenes-manual__actions">
              <Button variant="ghost" onClick={() => setMargenesManual(null)}>
                Cancelar
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setMargenes(margenesManual);
                  setMargenesManual(null);
                }}
              >
                Aplicar
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
