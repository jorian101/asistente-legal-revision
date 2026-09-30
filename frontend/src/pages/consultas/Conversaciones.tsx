// Conversaciones: gestion del historial del chat del usuario (chatStore).
//
// Reemplaza la tabla backend de Historial por un listado moderno en cards:
// - Dos modos: "Solo chats" (activas agrupadas por fecha + archivadas) y
//   "Por carpetas" (agrupadas por carpeta con seccion "Sin carpeta").
// - CRUD por card: Ver (abre el chat), Renombrar inline, Archivar/Desarchivar,
//   Mover a carpeta y Eliminar (soft delete con ConfirmDialog).
// - Busqueda por titulo/contenido de mensajes.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Archive,
  ArchiveRestore,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

import { useAuth } from "../../context/useAuth";
import { chatStore } from "../../lib/chatStore";
import type { Conversacion, EspacioTrabajo } from "../../lib/chatTypes";
import {
  GROUP_LABELS,
  getMonthName,
  groupConversacionesPorFecha,
} from "../../utils/chatGrouping";
import { PageHeader, Button } from "../../components/ui";
import ConfirmDialog from "../../components/ConfirmDialog";

import styles from "./Conversaciones.module.css";

type Modo = "todos" | "carpetas";

export default function Conversaciones() {
  const { auth } = useAuth();
  const navigate = useNavigate();
  const usuarioId = auth.id ?? 0;

  const [conversaciones, setConversaciones] = useState<Conversacion[]>([]);
  const [espacios, setEspacios] = useState<EspacioTrabajo[]>([]);
  const [modo, setModo] = useState<Modo>("todos");
  const [texto, setTexto] = useState("");
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [editandoTitulo, setEditandoTitulo] = useState("");
  const [confirmEliminarId, setConfirmEliminarId] = useState<string | null>(
    null,
  );
  const [menuAbiertoId, setMenuAbiertoId] = useState<string | null>(null);
  const [moverAbiertoId, setMoverAbiertoId] = useState<string | null>(null);

  const recargar = useCallback(() => {
    if (usuarioId === 0) {
      setConversaciones([]);
      setEspacios([]);
      return;
    }
    setConversaciones(chatStore.listarConversaciones(usuarioId));
    setEspacios(chatStore.listarEspacios(usuarioId));
  }, [usuarioId]);

  useEffect(() => {
    recargar();
  }, [recargar]);

  // Snippet y cantidad de mensajes por conversacion (para las cards).
  const detalle = useMemo(() => {
    const map = new Map<string, { snippet: string; total: number }>();
    for (const c of conversaciones) {
      const msgs = chatStore.listarMensajes(usuarioId, c.id);
      const ultimo = msgs[msgs.length - 1];
      map.set(c.id, { snippet: ultimo?.contenido ?? "", total: msgs.length });
    }
    return map;
  }, [usuarioId, conversaciones]);

  const visibles = useMemo(
    () =>
      texto.trim() === ""
        ? conversaciones
        : chatStore.buscarConversaciones(usuarioId, texto),
    [usuarioId, conversaciones, texto],
  );

  const activas = useMemo(
    () => visibles.filter((c) => c.estado === "activo"),
    [visibles],
  );
  const archivadas = useMemo(
    () => visibles.filter((c) => c.estado === "archivado"),
    [visibles],
  );

  const grupos = useMemo(() => groupConversacionesPorFecha(activas), [activas]);

  const porCarpeta = useMemo(() => {
    const map = new Map<string, Conversacion[]>();
    const sinCarpeta: Conversacion[] = [];
    for (const c of activas) {
      if (c.espacio_trabajo_id === null) {
        sinCarpeta.push(c);
      } else {
        const list = map.get(c.espacio_trabajo_id) ?? [];
        list.push(c);
        map.set(c.espacio_trabajo_id, list);
      }
    }
    return { map, sinCarpeta };
  }, [activas]);

  function abrirConversacion(id: string) {
    navigate(`/asistente/consultar?chat=${id}`);
  }

  function nuevaConversacion() {
    if (usuarioId === 0) return;
    const conv = chatStore.crearConversacion(usuarioId, "Sin titulo");
    recargar();
    abrirConversacion(conv.id);
  }

  function iniciarRename(c: Conversacion) {
    setEditandoId(c.id);
    setEditandoTitulo(c.titulo);
    setMenuAbiertoId(null);
  }

  function guardarRename() {
    if (editandoId !== null) {
      const nuevo = editandoTitulo.trim();
      if (nuevo) chatStore.renombrarConversacion(usuarioId, editandoId, nuevo);
    }
    setEditandoId(null);
    setEditandoTitulo("");
    recargar();
  }

  function archivar(c: Conversacion) {
    if (c.estado === "archivado") {
      chatStore.desarchivarConversacion(usuarioId, c.id);
    } else {
      chatStore.archivarConversacion(usuarioId, c.id);
    }
    setMenuAbiertoId(null);
    recargar();
  }

  function eliminarConfirmado() {
    if (confirmEliminarId !== null) {
      chatStore.eliminarConversacion(usuarioId, confirmEliminarId);
    }
    setConfirmEliminarId(null);
    setMenuAbiertoId(null);
    recargar();
  }

  function moverA(chatId: string, espacioId: string | null) {
    chatStore.moverACarpeta(usuarioId, chatId, espacioId);
    setMenuAbiertoId(null);
    setMoverAbiertoId(null);
    recargar();
  }

  function renderCard(c: Conversacion) {
    const d = detalle.get(c.id);
    const editando = editandoId === c.id;
    const carpeta = espacios.find((e) => e.id === c.espacio_trabajo_id);
    const menuAbierto = menuAbiertoId === c.id;
    const moverAbierto = moverAbiertoId === c.id;

    return (
      <article
        key={c.id}
        className={styles.card}
        onClick={() => abrirConversacion(c.id)}
      >
        <div className={styles.card__head}>
          {editando ? (
            <input
              className={styles.card__input}
              value={editandoTitulo}
              autoFocus
              onChange={(e) => setEditandoTitulo(e.target.value)}
              onBlur={guardarRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") guardarRename();
                if (e.key === "Escape") {
                  setEditandoId(null);
                  setEditandoTitulo("");
                }
              }}
              onClick={(e) => e.stopPropagation()}
              aria-label="Nombre de la conversacion"
            />
          ) : (
            <h3 className={styles.card__titulo}>{c.titulo}</h3>
          )}
          {!editando && (
            <button
              type="button"
              className={styles.card__menu}
              aria-label={`Opciones de ${c.titulo}`}
              aria-expanded={menuAbierto}
              onClick={(e) => {
                e.stopPropagation();
                setMenuAbiertoId(menuAbierto ? null : c.id);
                setMoverAbiertoId(null);
              }}
            >
              <MoreHorizontal size={16} aria-hidden="true" />
            </button>
          )}
        </div>

        {d && d.snippet !== "" && (
          <p className={styles.card__snippet}>{d.snippet}</p>
        )}

        <div className={styles.card__meta}>
          <span>
            {new Date(c.ultimo_mensaje_at ?? c.created_at).toLocaleDateString()}
          </span>
          <span>{d?.total ?? 0} mensajes</span>
          {c.estado === "archivado" && (
            <span className={styles.badge}>Archivada</span>
          )}
          {carpeta && (
            <span className={styles.card__carpeta}>{carpeta.nombre}</span>
          )}
        </div>

        {menuAbierto && (
          <div
            className={styles.menu}
            onClick={(e) => e.stopPropagation()}
            role="menu"
          >
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => abrirConversacion(c.id)}
            >
              Ver
            </button>
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => iniciarRename(c)}
            >
              <Pencil size={14} aria-hidden="true" /> Renombrar
            </button>
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => archivar(c)}
            >
              {c.estado === "archivado" ? (
                <ArchiveRestore size={14} aria-hidden="true" />
              ) : (
                <Archive size={14} aria-hidden="true" />
              )}
              {c.estado === "archivado" ? "Desarchivar" : "Archivar"}
            </button>
            <button
              type="button"
              className={styles.menu__item}
              onClick={() => setMoverAbiertoId(moverAbierto ? null : c.id)}
              aria-expanded={moverAbierto}
            >
              <FolderPlus size={14} aria-hidden="true" /> Mover a carpeta
            </button>
            {moverAbierto && (
              <div className={styles.menu__sub} role="menu">
                <button
                  type="button"
                  className={styles.menu__item}
                  onClick={() => moverA(c.id, null)}
                >
                  Sin carpeta
                </button>
                {espacios.map((e) => (
                  <button
                    key={e.id}
                    type="button"
                    className={styles.menu__item}
                    onClick={() => moverA(c.id, e.id)}
                  >
                    {e.nombre}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              className={`${styles.menu__item} ${styles["menu__item--danger"]}`}
              onClick={() => setConfirmEliminarId(c.id)}
            >
              <Trash2 size={14} aria-hidden="true" /> Eliminar
            </button>
          </div>
        )}
      </article>
    );
  }

  const confirmado = conversaciones.find((c) => c.id === confirmEliminarId);

  return (
    <div className={styles.pagina}>
      <PageHeader
        title="Conversaciones"
        subtitle="Historial de tus consultas: todas o agrupadas por carpeta."
        actions={
          <Button onClick={nuevaConversacion}>Nueva conversación</Button>
        }
      />

      <div className={styles.toolbar}>
        <div className={styles.seg} role="group" aria-label="Modo de vista">
          <button
            type="button"
            className={`${styles.seg__btn} ${modo === "todos" ? styles["seg__btn--active"] : ""}`}
            onClick={() => setModo("todos")}
          >
            Solo chats
          </button>
          <button
            type="button"
            className={`${styles.seg__btn} ${modo === "carpetas" ? styles["seg__btn--active"] : ""}`}
            onClick={() => setModo("carpetas")}
          >
            Por carpetas
          </button>
        </div>
        <input
          className={styles.search}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Buscar conversaciones..."
          aria-label="Buscar conversaciones"
        />
      </div>

      {activas.length === 0 && archivadas.length === 0 ? (
        <div className={styles.vacio}>
          <p>No hay conversaciones todavía.</p>
          <Button onClick={nuevaConversacion}>Iniciar primera consulta</Button>
        </div>
      ) : modo === "todos" ? (
        <div className={styles.lista}>
          {(["hoy", "ayer", "ultimos7dias", "esteMes"] as const).map(
            (k) =>
              grupos[k].length > 0 && (
                <section key={k} className={styles.seccion}>
                  <h4 className={styles.seccion__titulo}>{GROUP_LABELS[k]}</h4>
                  {grupos[k].map(renderCard)}
                </section>
              ),
          )}
          {Object.entries(grupos.meses)
            .sort(([a], [b]) => b.localeCompare(a))
            .map(
              ([monthKey, list]) =>
                list.length > 0 && (
                  <section key={monthKey} className={styles.seccion}>
                    <h4 className={styles.seccion__titulo}>
                      {getMonthName(
                        Number(monthKey.split("-")[1]),
                        Number(monthKey.split("-")[0]),
                      )}
                    </h4>
                    {list.map(renderCard)}
                  </section>
                ),
            )}
          {Object.entries(grupos.anios)
            .sort(([a], [b]) => Number(b) - Number(a))
            .map(
              ([yearKey, list]) =>
                list.length > 0 && (
                  <section key={yearKey} className={styles.seccion}>
                    <h4 className={styles.seccion__titulo}>{yearKey}</h4>
                    {list.map(renderCard)}
                  </section>
                ),
            )}
          {archivadas.length > 0 && (
            <section className={styles.seccion}>
              <h4 className={styles.seccion__titulo}>Archivadas</h4>
              {archivadas.map(renderCard)}
            </section>
          )}
        </div>
      ) : (
        <div className={styles.lista}>
          {porCarpeta.map.size > 0 &&
            espacios
              .filter((e) => (porCarpeta.map.get(e.id)?.length ?? 0) > 0)
              .map((e) => (
                <section key={e.id} className={styles.seccion}>
                  <h4 className={styles.seccion__titulo}>
                    {e.nombre} ({porCarpeta.map.get(e.id)!.length})
                  </h4>
                  {porCarpeta.map.get(e.id)!.map(renderCard)}
                </section>
              ))}
          {porCarpeta.sinCarpeta.length > 0 && (
            <section className={styles.seccion}>
              <h4 className={styles.seccion__titulo}>
                Sin carpeta ({porCarpeta.sinCarpeta.length})
              </h4>
              {porCarpeta.sinCarpeta.map(renderCard)}
            </section>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmEliminarId !== null}
        title="Eliminar conversación"
        message={
          confirmado ? (
            <>
              ¿Seguro que deseas eliminar <strong>{confirmado.titulo}</strong>?
              La conversación se moverá a eliminados y dejará de aparecer en la
              lista.
            </>
          ) : null
        }
        confirmLabel="Eliminar"
        cancelLabel="Cancelar"
        danger
        onConfirm={eliminarConfirmado}
        onCancel={() => setConfirmEliminarId(null)}
      />
    </div>
  );
}
