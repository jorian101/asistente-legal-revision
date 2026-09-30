// Mis Borradores: listado de los borradores del usuario estilo Conversaciones.
//
// Reemplaza la interfaz anterior de Borradores (que tenia su propio form de
// generacion). Ahora la generacion vive SOLO en el chat de Consultar; esta
// pagina lista los borradores guardados con dos acciones por card:
// - "Ver el chat" — navega a la conversacion donde se genero.
// - "Ver borrador final" — abre el detalle (contenido + autor + acciones).
//
// Regla 7: el backend filtra por propietario_id del JWT.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, MessageSquare, Download } from "lucide-react";

import {
  type BorradorBloqueDTO,
  type BorradorDTO,
  TIPO_BORRADOR_LABEL,
  actualizarBorrador,
  aprobarOficialBorrador,
  desoficializarBorrador,
  eliminarBorrador,
  exportarBorrador,
  listarMisBorradores,
  obtenerContextoExport,
  publicarBorrador,
  solicitarOficialBorrador,
} from "../../api/borradores";
import { chatStore } from "../../lib/chatStore";
import { useAuth } from "../../context/useAuth";
import { usePermisos } from "../../context/usePermisos";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import ConfirmDialog from "../../components/ConfirmDialog";
import { PageHeader, Button } from "../../components/ui";
import DocumentoPreview, {
  type MargenesMM,
  type PreviewOverride,
  type TamanoHoja,
} from "../admin/DocumentoPreview";
import FormatoEditor, { type CambioBloque } from "../admin/FormatoEditor";
import {
  bloquesEfectivos,
  bloquesToContenido,
  bloquesToLayout,
  bloquesToPreviewBloques,
  textoPlano,
  type BloqueBorradorDTO,
} from "../../lib/borradorBlocks";
import { useHistorial } from "../../lib/useHistorial";

import "./MisBorradores.css";

const ESTADO_LABEL: Record<string, string> = {
  borrador: "Borrador",
  publicado: "Publicado",
  pendiente_oficial: "Pendiente de oficial",
  oficial: "Oficial",
};

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

export default function MisBorradores() {
  const { auth } = useAuth();
  const puedeEliminar = usePermisos().puede("borradores", "eliminar");
  const navigate = useNavigate();
  const usuarioId = auth.id ?? 0;

  const [borradores, setBorradores] = useState<BorradorDTO[]>([]);
  const [detalle, setDetalle] = useState<BorradorDTO | null>(null);
  const [confirmEliminarId, setConfirmEliminarId] = useState<number | null>(
    null,
  );
  const [eliminando, setEliminando] = useState<number | null>(null);
  const [publicando, setPublicando] = useState(false);
  // Solicitar / aprobar / desoficializar en curso: evita el doble envío.
  const [cambiandoEstado, setCambiandoEstado] = useState(false);
  // Desoficializar cambia un estado del que dependen otros: se confirma.
  const [confirmDesoficializar, setConfirmDesoficializar] = useState(false);
  const [exportando, setExportando] = useState(false);

  const recargar = useCallback(() => {
    let cancelado = false;
    listarMisBorradores()
      .then((items) => {
        if (!cancelado) setBorradores(items);
      })
      .catch((err) => {
        if (!cancelado)
          toast(mensajeError(err, "No se pudo cargar los borradores"), "error");
      });
    return () => {
      cancelado = true;
    };
  }, []);

  useEffect(() => recargar(), [recargar]);

  // Mapa chat_id_bd (BD) -> conversacion local (chatStore) para "Ver el chat".
  const conversacionPorChatBd = useMemo(() => {
    const map = new Map<number, string>();
    if (usuarioId === 0) return map;
    for (const c of chatStore.listarConversaciones(usuarioId)) {
      if (c.chat_id_bd !== null && c.chat_id_bd !== undefined) {
        map.set(c.chat_id_bd, c.id);
      }
    }
    return map;
  }, [usuarioId]);

  function verChat(b: BorradorDTO) {
    if (b.chat_id === null) {
      toast("Este borrador no está vinculado a un chat.", "info");
      return;
    }
    const convId = conversacionPorChatBd.get(b.chat_id);
    navigate(
      convId ? `/asistente/consultar?chat=${convId}` : "/asistente/consultar",
    );
  }

  async function confirmarEliminar() {
    if (confirmEliminarId === null) return;
    const id = confirmEliminarId;
    setConfirmEliminarId(null);
    setEliminando(id);
    try {
      await eliminarBorrador(id);
      toast("Obrado eliminado.", "success");
      setBorradores((prev) => prev.filter((b) => b.id !== id));
    } catch (err) {
      toast(mensajeError(err, "No se pudo eliminar el obrado."), "error");
    } finally {
      setEliminando(null);
    }
  }

  async function publicar() {
    if (detalle === null) return;
    setPublicando(true);
    try {
      await publicarBorrador(detalle.id);
      toast("Borrador publicado.", "success");
      const items = await listarMisBorradores();
      setBorradores(items);
      setDetalle(items.find((b) => b.id === detalle.id) ?? null);
    } catch (err) {
      toast(mensajeError(err, "No se pudo publicar"), "error");
    } finally {
      setPublicando(false);
    }
  }

  async function exportar() {
    if (detalle === null) return;
    setExportando(true);
    try {
      const blob = await exportarBorrador(detalle.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `borrador_${detalle.id}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(mensajeError(err, "No se pudo exportar"), "error");
    } finally {
      setExportando(false);
    }
  }

  async function guardarEdicion(contenido: string) {
    if (detalle === null) return;
    try {
      const actualizado = await actualizarBorrador(detalle.id, contenido);
      setDetalle(actualizado);
      setBorradores((prev) =>
        prev.map((b) => (b.id === actualizado.id ? actualizado : b)),
      );
      toast("Borrador actualizado.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo guardar"), "error");
      throw err;
    }
  }

  async function guardarEdicionFiel(
    contenido: string,
    layout: BorradorBloqueDTO[],
  ) {
    if (detalle === null) return;
    try {
      const actualizado = await actualizarBorrador(
        detalle.id,
        contenido,
        layout,
      );
      setDetalle(actualizado);
      setBorradores((prev) =>
        prev.map((b) => (b.id === actualizado.id ? actualizado : b)),
      );
      toast("Borrador guardado (md + fiel).", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo guardar"), "error");
      throw err;
    }
  }

  async function solicitarOficial() {
    if (detalle === null) return;
    setCambiandoEstado(true);
    try {
      const actualizado = await solicitarOficialBorrador(detalle.id);
      setDetalle(actualizado);
      setBorradores((prev) =>
        prev.map((b) => (b.id === actualizado.id ? actualizado : b)),
      );
      toast("Solicitud de oficial enviada al supervisor.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo solicitar oficial"), "error");
    } finally {
      setCambiandoEstado(false);
    }
  }

  async function aprobarOficial() {
    if (detalle === null) return;
    setCambiandoEstado(true);
    try {
      const actualizado = await aprobarOficialBorrador(detalle.id);
      setDetalle(actualizado);
      setBorradores((prev) =>
        prev.map((b) => (b.id === actualizado.id ? actualizado : b)),
      );
      toast("Obrado aprobado como oficial.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo aprobar oficial"), "error");
    } finally {
      setCambiandoEstado(false);
    }
  }

  async function desoficializar(
    destino: "pendiente_oficial" | "publicado" | "borrador",
  ) {
    if (detalle === null) return;
    setCambiandoEstado(true);
    try {
      const actualizado = await desoficializarBorrador(detalle.id, destino);
      setDetalle(actualizado);
      setBorradores((prev) =>
        prev.map((b) => (b.id === actualizado.id ? actualizado : b)),
      );
      toast("Obrado desoficializado.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo desoficializar"), "error");
    } finally {
      setCambiandoEstado(false);
    }
  }

  return (
    <div className="mis-borradores">
      <PageHeader
        title="Mis Obrados"
        subtitle="Autos de vista y dictámenes que generaste en el chat."
      />

      {borradores.length === 0 ? (
        <p className="mis-borradores__vacio">
          Todavía no guardaste obrados. Generá uno en el chat de Consultar
          (adjuntá un expediente con obrados) y pulsá "Guardar en Mis
          Borradores" sobre la respuesta.
        </p>
      ) : (
        <div className="mis-borradores__grid">
          {borradores.map((b) => (
            <CardBorrador
              key={b.id}
              borrador={b}
              onVerChat={() => verChat(b)}
              onVerDetalle={() => setDetalle(b)}
              onEliminar={
                puedeEliminar ? () => setConfirmEliminarId(b.id) : null
              }
            />
          ))}
        </div>
      )}

      {confirmEliminarId !== null && (
        <ConfirmDialog
          open={confirmEliminarId !== null}
          title="Eliminar obrado"
          message={
            <>
              ¿Eliminar este obrado? Quedará oculto en tus borradores; la acción
              es recuperable solo por administración.
            </>
          }
          confirmLabel="Eliminar"
          cancelLabel="Cancelar"
          danger
          busy={eliminando === confirmEliminarId}
          onConfirm={() => void confirmarEliminar()}
          onCancel={() => setConfirmEliminarId(null)}
        />
      )}

      <ConfirmDialog
        open={confirmDesoficializar}
        title="Desoficializar obrado"
        message="El obrado deja de ser oficial, vuelve a publicado y deja de contar como resolución del tribunal en la jurisprudencia."
        confirmLabel="Desoficializar"
        danger
        busy={cambiandoEstado}
        onConfirm={() =>
          void desoficializar("publicado").finally(() =>
            setConfirmDesoficializar(false),
          )
        }
        onCancel={() => setConfirmDesoficializar(false)}
      />

      {detalle !== null && (
        <DetalleBorrador
          borrador={detalle}
          onCerrar={() => setDetalle(null)}
          onPublicar={() => void publicar()}
          onExportar={() => void exportar()}
          onGuardarEdit={guardarEdicion}
          onGuardarFiel={guardarEdicionFiel}
          onSolicitarOficial={() => void solicitarOficial()}
          onAprobarOficial={() => void aprobarOficial()}
          onDesoficializar={(destino) =>
            destino === "publicado"
              ? setConfirmDesoficializar(true)
              : void desoficializar(destino)
          }
          publicando={publicando}
          exportando={exportando}
          cambiandoEstado={cambiandoEstado}
        />
      )}
    </div>
  );
}

function CardBorrador({
  borrador,
  onVerChat,
  onVerDetalle,
  onEliminar,
}: {
  borrador: BorradorDTO;
  onVerChat: () => void;
  onVerDetalle: () => void;
  /** null = sin permiso de eliminar (el botón no se muestra). */
  onEliminar: (() => void) | null;
}) {
  const autor =
    borrador.autor_nombre !== null
      ? `${borrador.autor_nombre}${borrador.autor_cargo ? ` · ${borrador.autor_cargo}` : ""}`
      : null;
  return (
    <article className="mis-borradores__card">
      <div className="mis-borradores__header">
        <span className="mis-borradores__tipo">
          {TIPO_BORRADOR_LABEL[
            borrador.tipo as keyof typeof TIPO_BORRADOR_LABEL
          ] ?? borrador.tipo}
        </span>
        <span
          className={`mis-borradores__badge mis-borradores__badge--${borrador.estado}`}
        >
          {ESTADO_LABEL[borrador.estado] ?? borrador.estado}
        </span>
      </div>
      {autor && (
        <span className="mis-borradores__autor">Generado por {autor}</span>
      )}
      <span className="mis-borradores__expediente">
        Expediente #{borrador.expediente_id}
      </span>
      <p className="mis-borradores__preview">
        {textoPlano(borrador.contenido)}
      </p>
      <span className="mis-borradores__fecha">
        Actualizado {formatFecha(borrador.updated_at ?? borrador.created_at)}
      </span>
      <div className="mis-borradores__acciones">
        <Button
          variant="secondary"
          onClick={onVerChat}
          title="Abrir la conversación donde se generó este obrado"
        >
          <MessageSquare size={14} aria-hidden="true" />
          Ver el chat
        </Button>
        <Button
          variant="primary"
          onClick={onVerDetalle}
          title="Ver el texto completo y las acciones (publicar, oficial…)"
        >
          <Eye size={14} aria-hidden="true" />
          Ver obrado final
        </Button>
        {onEliminar && (
          <Button
            variant="secondary"
            onClick={onEliminar}
            title="Eliminar este obrado (soft delete)"
          >
            Eliminar
          </Button>
        )}
      </div>
    </article>
  );
}

function DetalleBorrador({
  borrador,
  onCerrar,
  onPublicar,
  onExportar,
  onGuardarEdit: _onGuardarEdit,
  onGuardarFiel,
  onSolicitarOficial,
  onAprobarOficial,
  onDesoficializar,
  publicando,
  exportando,
  cambiandoEstado,
}: {
  borrador: BorradorDTO;
  onCerrar: () => void;
  onPublicar: () => void;
  onExportar: () => void;
  onGuardarEdit: (contenido: string) => Promise<void>;
  onGuardarFiel: (
    contenido: string,
    layout: BorradorBloqueDTO[],
  ) => Promise<void>;
  onSolicitarOficial: () => void;
  onAprobarOficial: () => void;
  onDesoficializar: (
    destino: "pendiente_oficial" | "publicado" | "borrador",
  ) => void;
  publicando: boolean;
  exportando: boolean;
  cambiandoEstado: boolean;
}) {
  const { auth } = useAuth();
  const esSupervisor = auth.rol === "supervisor";
  const esPropietario = borrador.propietario_id === auth.id;
  // Editar, publicar y solicitar oficial exigen borradores.actualizar.
  const puedeActualizar = usePermisos().puede("borradores", "actualizar");
  // Editan: el dueño en 'borrador' y el supervisor durante la revision ('pendiente_oficial').
  // Un oficial no se edita: se desoficializa primero.
  const puedeEditar =
    puedeActualizar &&
    (borrador.estado === "borrador" ||
      (esSupervisor && borrador.estado === "pendiente_oficial"));
  const soloLectura = !puedeEditar;

  const baseBloques = useMemo(
    () =>
      bloquesEfectivos(
        borrador.contenido,
        borrador.layout as BloqueBorradorDTO[] | null,
      ),
    [borrador.contenido, borrador.layout],
  );

  const [tamano, setTamano] = useState<TamanoHoja>("carta");
  const [margenes, setMargenes] = useState<MargenesMM>({
    top: 25,
    right: 20,
    bottom: 20,
    left: 40,
  });
  // Ediciones pendientes con historial por pasos (Deshacer/Rehacer reales).
  const historial = useHistorial<
    Record<string, PreviewOverride & { heading?: number }>
  >({});
  const overrides = historial.estado;
  const { reiniciar: reiniciarHistorial, cambiar: cambiarOverrides } =
    historial;
  const [editandoKey, setEditandoKey] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    reiniciarHistorial({});
    setEditandoKey(null);
  }, [borrador.id, reiniciarHistorial]);

  useEffect(() => {
    void obtenerContextoExport(borrador.id)
      .then((ctx) => {
        if (
          ctx.tamano_hoja === "carta" ||
          ctx.tamano_hoja === "oficio" ||
          ctx.tamano_hoja === "a4"
        ) {
          setTamano(ctx.tamano_hoja as TamanoHoja);
        }
        setMargenes(ctx.margenes as MargenesMM);
      })
      .catch(() => {});
  }, [borrador.id]);

  function bloquesConOverride(): BloqueBorradorDTO[] {
    return baseBloques.map((b, i) => {
      const k = `p1:i${i}`;
      const ov = overrides[k];
      if (!ov) return b;
      return {
        ...b,
        texto: ov.texto ?? b.texto,
        align: (ov.align as string) ?? b.align,
        bold: ov.bold ?? b.bold,
        underline: ov.underline ?? b.underline,
        size_pt: ov.size_pt !== undefined ? ov.size_pt : b.size_pt,
        font:
          (ov.font as string | null) !== undefined
            ? (ov.font as string | null)
            : b.font,
        heading: (ov as { heading?: number }).heading ?? b.heading,
      };
    });
  }

  const previewBloques = bloquesToPreviewBloques(bloquesConOverride());
  const hayCambios = Object.keys(overrides).length > 0;

  function textoDeBloque(key: string): string {
    const idx = Number(key.split(":i")[1]);
    const b = bloquesConOverride()[idx];
    return b ? b.texto : "";
  }
  function estiloDeBloque(key: string) {
    const idx = Number(key.split(":i")[1]);
    const b = bloquesConOverride()[idx];
    if (!b)
      return {
        align: "justify",
        bold: false,
        underline: false,
        size_pt: null,
        font: null,
      };
    return {
      align: b.align,
      bold: b.bold,
      underline: b.underline,
      size_pt: b.size_pt,
      font: b.font,
    };
  }

  async function guardarTodo() {
    if (!hayCambios) {
      toast("No hay cambios pendientes.", "info");
      return;
    }
    const final = bloquesConOverride();
    const md = bloquesToContenido(final);
    const layout = bloquesToLayout(final);
    setGuardando(true);
    try {
      await onGuardarFiel(md, layout);
      reiniciarHistorial({});
      setEditandoKey(null);
    } finally {
      setGuardando(false);
    }
  }

  function handleCambio(key: string, c: CambioBloque) {
    // Lo tipeado seguido en el mismo bloque es un solo paso de Deshacer.
    cambiarOverrides(
      (prev) => ({
        ...prev,
        [key]: {
          texto: c.texto,
          align: c.align,
          bold: c.bold,
          underline: c.underline,
          size_pt: c.size_pt,
          font: c.font,
        },
      }),
      `editor:${key}`,
    );
  }

  function cerrarEdicion() {
    setEditandoKey(null);
  }

  const autor =
    borrador.autor_nombre !== null
      ? `${borrador.autor_nombre}${borrador.autor_cargo ? ` · ${borrador.autor_cargo}` : ""}`
      : null;

  // Cambios sin guardar: cerrar pide confirmación y el navegador avisa antes de salir.
  // Publicar/solicitar/aprobar con cambios pendientes publicaba la versión guardada vieja.
  const cambiosPendientes = hayCambios && !soloLectura;
  const [confirmCerrar, setConfirmCerrar] = useState(false);
  useEffect(() => {
    if (!cambiosPendientes) return;
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [cambiosPendientes]);
  const cerrar = () =>
    cambiosPendientes ? setConfirmCerrar(true) : onCerrar();
  const guardeAntes = cambiosPendientes
    ? "Guarde los cambios antes de continuar"
    : undefined;

  return (
    <div
      className="mis-borradores__detalle"
      role="dialog"
      aria-modal="true"
      aria-label="Detalle del borrador"
    >
      <div className="mis-borradores__detalle-box mis-borradores__detalle-box--wide">
        <div className="mis-borradores__header">
          <div>
            <div className="mis-borradores__tipo">
              {TIPO_BORRADOR_LABEL[
                borrador.tipo as keyof typeof TIPO_BORRADOR_LABEL
              ] ?? borrador.tipo}
            </div>
            {autor && (
              <span className="mis-borradores__autor">
                Generado por {autor}
              </span>
            )}
          </div>
          <span
            className={`mis-borradores__badge mis-borradores__badge--${borrador.estado}`}
          >
            {ESTADO_LABEL[borrador.estado] ?? borrador.estado}
          </span>
        </div>

        {borrador.razonamiento && borrador.razonamiento.trim() !== "" && (
          <details className="mis-borradores__pensamiento" open={false}>
            <summary className="mis-borradores__pensamiento-toggle">
              <span aria-hidden="true">🧠</span>
              <span>Ver pensamiento del modelo</span>
            </summary>
            <div className="mis-borradores__pensamiento-caja">
              {borrador.razonamiento}
            </div>
          </details>
        )}

        {/* Una sola vista: el documento tal como se imprime (la pestaña Markdown mostraba el
            texto con marcas de formato, que no es algo para el usuario). */}
        <div className="mis-borradores__detalle-preview">
            <DocumentoPreview
              bloques={previewBloques}
              puedeEditar={!soloLectura}
              tamano={tamano}
              onTamanoChange={setTamano}
              margenes={margenes}
              onMargenesChange={setMargenes}
              onAplicarSeleccion={(claves, cambio) => {
                if (soloLectura) return;
                cambiarOverrides((prev) => {
                  const n = { ...prev };
                  for (const k of claves) n[k] = { ...prev[k], ...cambio };
                  return n;
                });
              }}
              editandoKey={editandoKey}
              onEditarBloque={(k) => {
                if (soloLectura) return;
                setEditandoKey(k);
              }}
              onCerrarEdicion={cerrarEdicion}
              onDeshacer={historial.deshacer}
              canDeshacer={historial.puedeDeshacer && !soloLectura}
              onRehacer={historial.rehacer}
              canRehacer={historial.puedeRehacer && !soloLectura}
              onCancelarLocal={() => {
                reiniciarHistorial({});
                setEditandoKey(null);
              }}
              onGuardarTodo={soloLectura ? undefined : () => void guardarTodo()}
              hayCambios={hayCambios && !soloLectura}
              saving={guardando}
              editorSlot={
                editandoKey
                  ? (() => {
                      const key = editandoKey;
                      const estilo = estiloDeBloque(key);
                      return (
                        <FormatoEditor
                          inicial={textoDeBloque(key)}
                          estiloInicial={{
                            align: estilo.align,
                            bold: estilo.bold,
                            underline: estilo.underline,
                            size_pt: estilo.size_pt,
                            font: estilo.font,
                          }}
                          onCambio={(c) => handleCambio(key, c)}
                          onGuardar={(c) => {
                            handleCambio(key, c);
                            setEditandoKey(null);
                          }}
                          onCancelar={() => {
                            cambiarOverrides((prev) => {
                              const n = { ...prev };
                              delete n[key];
                              return n;
                            });
                            setEditandoKey(null);
                          }}
                          disabled={guardando}
                          modo="inline"
                        />
                      );
                    })()
                  : undefined
              }
            />
            {soloLectura && (
              <p className="mis-borradores__detalle-hint">
                Solo lectura: el obrado está {borrador.estado}.
                {borrador.estado === "oficial"
                  ? " Un obrado oficial no se edita: el supervisor debe volverlo primero a solicitud de oficialización."
                  : " Solo se edita un obrado en borrador, o en revisión por el supervisor."}
              </p>
            )}
            {hayCambios && !soloLectura && (
              <p className="mis-borradores__detalle-hint">
                Cambios sin guardar. Presione «Guardar todo» para que se
                reflejen en el Word y el PDF.
              </p>
            )}
          </div>

        <div className="mis-borradores__detalle-acciones">
          <Button variant="ghost" onClick={cerrar}>
            Cerrar
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setEditandoKey(null); // que no se imprima el editor abierto
              setTimeout(() => window.print(), 0);
            }}
            disabled={cambiosPendientes}
            title={guardeAntes ?? "Exportar como PDF (imprimir)"}
          >
            Exportar PDF
          </Button>
          <Button
            variant="secondary"
            onClick={onExportar}
            disabled={exportando || hayCambios}
            title={
              hayCambios
                ? "Guarde los cambios antes de exportar el Word"
                : "Exportar Word (.docx)"
            }
          >
            <Download size={14} aria-hidden="true" />
            Word
          </Button>
          {puedeEditar && (
            <Button
              variant="primary"
              onClick={() => void guardarTodo()}
              disabled={!hayCambios || guardando}
            >
              {guardando ? "Guardando..." : "Guardar todo"}
            </Button>
          )}
          {puedeActualizar && borrador.estado === "borrador" && (
            <Button
              variant="primary"
              onClick={onPublicar}
              disabled={publicando || cambiosPendientes}
              title={guardeAntes}
            >
              {publicando ? "Publicando..." : "Publicar"}
            </Button>
          )}
          {puedeActualizar &&
            esPropietario &&
            borrador.estado === "publicado" && (
              <Button
                variant="primary"
                onClick={onSolicitarOficial}
                loading={cambiandoEstado}
                disabled={cambiosPendientes}
                title={guardeAntes}
              >
                Solicitar oficial
              </Button>
            )}
          {esSupervisor && borrador.estado === "pendiente_oficial" && (
            <Button
              variant="primary"
              onClick={onAprobarOficial}
              loading={cambiandoEstado}
              disabled={cambiosPendientes}
              title={guardeAntes}
            >
              Aprobar oficial
            </Button>
          )}
          {esSupervisor && borrador.estado === "oficial" && (
            <>
              <Button
                variant="primary"
                onClick={() => onDesoficializar("pendiente_oficial")}
                disabled={cambiandoEstado}
              >
                Volver a solicitud de oficialización
              </Button>
              <Button
                variant="secondary"
                onClick={() => onDesoficializar("publicado")}
                disabled={cambiandoEstado}
              >
                Desoficializar
              </Button>
              <Button
                variant="ghost"
                onClick={() => onDesoficializar("borrador")}
                disabled={cambiandoEstado}
              >
                Devolver a borrador
              </Button>
            </>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirmCerrar}
        title="Descartar cambios"
        message="Hay cambios sin guardar en este obrado. Si cierra ahora, se perderán."
        confirmLabel="Descartar y cerrar"
        cancelLabel="Seguir editando"
        danger
        onConfirm={() => {
          setConfirmCerrar(false);
          onCerrar();
        }}
        onCancel={() => setConfirmCerrar(false)}
      />
    </div>
  );
}
