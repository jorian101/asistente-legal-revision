// ChatSidebar: sidebar del asistente. Lista los chats sueltos agrupados por
// fecha, las carpetas (Fijados, Archivados y personalizadas) y los botones
// de accion (nueva conversacion / buscar / archivados / nueva carpeta).

import { useMemo, useState } from "react";
import {
  Archive,
  MessageSquarePlus,
  Search,
  FolderPlus,
  X,
} from "lucide-react";

import type { Conversacion, EspacioTrabajo } from "../../lib/chatTypes";
import {
  GROUP_LABELS,
  getMonthName,
  groupConversacionesPorFecha,
} from "../../utils/chatGrouping";

import { ChatItem } from "./ChatItem";
import { FolderItem } from "./FolderItem";
import { SearchModal } from "./SearchModal";
import { ArchivedChatsModal } from "./ArchivedChatsModal";

import styles from "./ChatSidebar.module.css";

interface Props {
  conversaciones: Conversacion[];
  espacios: EspacioTrabajo[];
  conversacionActivaId: string | null;
  onSeleccionarConversacion: (id: string) => void;
  onRenombrarConversacion: (id: string, titulo: string) => void;
  onEliminarConversacion: (id: string) => void;
  onArchivarConversacion: (id: string) => void;
  onDesarchivarConversacion: (id: string) => void;
  onFijarConversacion: (id: string) => void;
  onDesfijarConversacion: (id: string) => void;
  onMoverACarpeta: (id: string, espacioId: string | null) => void;
  onNuevaConversacion: () => void;
  /** F1: ids de chats con una generación en curso (indicador en el item). */
  chatsGenerando?: ReadonlySet<string>;
  /** Cierra el panel (botón visible solo en móvil, donde es un drawer). */
  onCerrar: () => void;
  onBuscar: (query: string) => Conversacion[];
  onCrearCarpeta: (nombre: string) => string;
  onRenombrarEspacio: (id: string, nombre: string) => void;
  onEliminarEspacio: (id: string) => void;
}

export function ChatSidebar({
  conversaciones,
  espacios,
  conversacionActivaId,
  onSeleccionarConversacion,
  onRenombrarConversacion,
  onEliminarConversacion,
  onArchivarConversacion,
  onDesarchivarConversacion,
  onFijarConversacion,
  onDesfijarConversacion,
  onMoverACarpeta,
  onNuevaConversacion,
  chatsGenerando,
  onCerrar,
  onBuscar,
  onCrearCarpeta,
  onRenombrarEspacio,
  onEliminarEspacio,
}: Props) {
  const [buscarAbierto, setBuscarAbierto] = useState(false);
  const [archivadosAbierto, setArchivadosAbierto] = useState(false);
  const [nuevaCarpetaId, setNuevaCarpetaId] = useState<string | null>(null);

  const archivadas = useMemo(
    () => conversaciones.filter((c) => c.estado === "archivado"),
    [conversaciones],
  );

  const conversacionesPorEspacio = useMemo(() => {
    const map = new Map<string, Conversacion[]>();
    for (const c of conversaciones) {
      if (c.estado !== "activo" || c.espacio_trabajo_id === null) continue;
      const list = map.get(c.espacio_trabajo_id) ?? [];
      list.push(c);
      map.set(c.espacio_trabajo_id, list);
    }
    return map;
  }, [conversaciones]);

  const sueltos = useMemo(
    () =>
      conversaciones.filter(
        (c) =>
          c.estado === "activo" &&
          c.espacio_trabajo_id === null &&
          c.prioridad !== "alta", // las prioritarias siguen mostrandose; las activas sin carpeta se agrupan
      ),
    [conversaciones],
  );

  const grupos = useMemo(() => groupConversacionesPorFecha(sueltos), [sueltos]);

  function handleNuevaCarpeta() {
    // Crea la carpeta al instante con "Sin título" y entra en modo edicion
    // inline para que el usuario la renombre.
    const id = onCrearCarpeta("Sin título");
    setNuevaCarpetaId(id);
  }

  function handleRenombrarEspacio(id: string, nombre: string) {
    onRenombrarEspacio(id, nombre);
    if (id === nuevaCarpetaId) setNuevaCarpetaId(null);
  }

  function handleDragStart(e: React.DragEvent, chatId: string) {
    e.dataTransfer.setData("application/x-chat-id", chatId);
    e.dataTransfer.effectAllowed = "move";
  }

  return (
    <aside
      id="historial-chat"
      className={styles.sidebar}
      aria-label="Historial de conversaciones"
    >
      <div className={styles.header}>
        <h2 className={styles.title}>Conversaciones</h2>
        <button
          type="button"
          className={styles.cerrar}
          onClick={onCerrar}
          aria-label="Cerrar historial"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <nav className={styles.nav} aria-label="Acciones del chat">
        <button
          type="button"
          className={styles.navBtn}
          onClick={onNuevaConversacion}
        >
          <MessageSquarePlus size={16} aria-hidden="true" />
          Nueva conversacion
        </button>
        <button
          type="button"
          className={styles.navBtn}
          onClick={() => setBuscarAbierto(true)}
        >
          <Search size={16} aria-hidden="true" />
          Buscar
        </button>
        <button
          type="button"
          className={styles.navBtn}
          onClick={() => setArchivadosAbierto(true)}
        >
          <Archive size={16} aria-hidden="true" />
          Archivados ({archivadas.length})
        </button>
        <button
          type="button"
          className={styles.navBtn}
          onClick={handleNuevaCarpeta}
        >
          <FolderPlus size={16} aria-hidden="true" />
          Nueva carpeta
        </button>
      </nav>

      <div className={styles.body}>
        {espacios.length > 0 && (
          <div className={styles.section}>
            <h3 className={styles.section__title}>Carpetas</h3>
            {espacios.map((esp) => (
              <FolderItem
                key={esp.id}
                espacio={esp}
                chats={conversacionesPorEspacio.get(esp.id) ?? []}
                conversacionActivaId={conversacionActivaId}
                autoEdit={esp.id === nuevaCarpetaId}
                chatsGenerando={chatsGenerando}
                onSelectChat={onSeleccionarConversacion}
                onRename={handleRenombrarEspacio}
                onDelete={onEliminarEspacio}
                onRenameChat={onRenombrarConversacion}
                onDeleteChat={onEliminarConversacion}
                onPinChat={onFijarConversacion}
                onUnpinChat={onDesfijarConversacion}
                onArchiveChat={onArchivarConversacion}
                onDropChat={(chatId, espacioId) =>
                  onMoverACarpeta(chatId, espacioId)
                }
              />
            ))}
          </div>
        )}

        <div className={styles.section}>
          <h3 className={styles.section__title}>Recientes</h3>
          {sueltos.length === 0 ? (
            <div className={styles.empty}>
              <p>
                Inicia una consulta y la conversacion aparecera aqui para que
                puedas retomarla despues.
              </p>
              <button
                type="button"
                className={styles.empty__cta}
                onClick={onNuevaConversacion}
              >
                Empezar primera consulta
              </button>
            </div>
          ) : (
            <>
              {(["hoy", "ayer", "ultimos7dias", "esteMes"] as const).map(
                (k) =>
                  grupos[k].length > 0 && (
                    <div key={k}>
                      <h4 className={styles.section__title}>
                        {GROUP_LABELS[k]}
                      </h4>
                      {grupos[k].map((c) => (
                        <ChatItem
                          key={c.id}
                          conversacion={c}
                          selected={conversacionActivaId === c.id}
                          isPinned={false}
                          generando={chatsGenerando?.has(c.id) ?? false}
                          onSelect={() => onSeleccionarConversacion(c.id)}
                          onRename={(nuevo) =>
                            onRenombrarConversacion(c.id, nuevo)
                          }
                          onPin={() => onFijarConversacion(c.id)}
                          onUnpin={() => onDesfijarConversacion(c.id)}
                          onArchive={() => onArchivarConversacion(c.id)}
                          onDelete={() => onEliminarConversacion(c.id)}
                          draggable
                          onDragStart={(e) => handleDragStart(e, c.id)}
                        />
                      ))}
                    </div>
                  ),
              )}
              {Object.entries(grupos.meses)
                .sort(([a], [b]) => b.localeCompare(a))
                .map(
                  ([monthKey, list]) =>
                    list.length > 0 && (
                      <div key={monthKey}>
                        <h4 className={styles.section__title}>
                          {getMonthName(
                            Number(monthKey.split("-")[1]),
                            Number(monthKey.split("-")[0]),
                          )}
                        </h4>
                        {list.map((c) => (
                          <ChatItem
                            key={c.id}
                            conversacion={c}
                            selected={conversacionActivaId === c.id}
                            isPinned={false}
                            generando={chatsGenerando?.has(c.id) ?? false}
                            onSelect={() => onSeleccionarConversacion(c.id)}
                            onRename={(nuevo) =>
                              onRenombrarConversacion(c.id, nuevo)
                            }
                            onPin={() => onFijarConversacion(c.id)}
                            onUnpin={() => onDesfijarConversacion(c.id)}
                            onArchive={() => onArchivarConversacion(c.id)}
                            onDelete={() => onEliminarConversacion(c.id)}
                            draggable
                            onDragStart={(e) => handleDragStart(e, c.id)}
                          />
                        ))}
                      </div>
                    ),
                )}
              {Object.entries(grupos.anios)
                .sort(([a], [b]) => Number(b) - Number(a))
                .map(
                  ([yearKey, list]) =>
                    list.length > 0 && (
                      <div key={yearKey}>
                        <h4 className={styles.section__title}>{yearKey}</h4>
                        {list.map((c) => (
                          <ChatItem
                            key={c.id}
                            conversacion={c}
                            selected={conversacionActivaId === c.id}
                            isPinned={false}
                            generando={chatsGenerando?.has(c.id) ?? false}
                            onSelect={() => onSeleccionarConversacion(c.id)}
                            onRename={(nuevo) =>
                              onRenombrarConversacion(c.id, nuevo)
                            }
                            onPin={() => onFijarConversacion(c.id)}
                            onUnpin={() => onDesfijarConversacion(c.id)}
                            onArchive={() => onArchivarConversacion(c.id)}
                            onDelete={() => onEliminarConversacion(c.id)}
                            draggable
                            onDragStart={(e) => handleDragStart(e, c.id)}
                          />
                        ))}
                      </div>
                    ),
                )}
            </>
          )}
        </div>
      </div>

      <SearchModal
        open={buscarAbierto}
        onClose={() => setBuscarAbierto(false)}
        conversaciones={conversaciones.filter((c) => c.estado !== "eliminado")}
        espacios={espacios}
        onSelect={onSeleccionarConversacion}
        onBuscar={onBuscar}
        onRenombrar={onRenombrarConversacion}
        onEliminar={onEliminarConversacion}
      />

      <ArchivedChatsModal
        open={archivadosAbierto}
        onClose={() => setArchivadosAbierto(false)}
        conversaciones={archivadas}
        onDesarchivar={onDesarchivarConversacion}
        onEliminar={onEliminarConversacion}
        onSeleccionar={onSeleccionarConversacion}
      />
    </aside>
  );
}
