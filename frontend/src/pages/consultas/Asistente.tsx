// Asistente: interfaz conversacional del asistente juridico.
//
// Estructura: ChatSidebar (carpetas/archivados/busqueda) + area de chat
// (MessagesScroll + InputArea). El estado de conversaciones vive en
// chatStore (localStorage) hasta que Sprint 4 conecte el backend.
//
// Lee el usuarioId del auth.carnet para el scoping del store local.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, FolderOpen, History, X } from "lucide-react";

import {
  eliminarHistorial,
  obtenerFuentesConsulta,
  responderConsulta,
} from "../../api/consultas";
import { chatStore } from "../../lib/chatStore";
import {
  asegurarChatPersistido,
  hidratarMensajes,
  persistirMensajeEnChat,
} from "../../lib/persistirChat";
import { guardarBorrador } from "../../api/borradores";
import {
  getRequisitosFaltantes,
  listarHistorialExpediente,
} from "../../api/expedientes";
import type {
  Conversacion,
  EspacioTrabajo,
  Mensaje,
} from "../../lib/chatTypes";
import { useAuth } from "../../context/useAuth";
import { usePermisos } from "../../context/usePermisos";
import { mensajeError } from "../../lib/errors";
import {
  esperarRespuestaFinal,
  guardarPendiente,
  leerPendiente,
  limpiarPendiente,
} from "../../lib/streamResume";

import { ChatSidebar } from "../../components/chat/ChatSidebar";
import { IconoCategoria } from "../../components/chat/IconoCategoria";
import { SelectorFuentes } from "../../components/chat/SelectorFuentes";
import { categoriaDeRef } from "../../lib/categoriaRef";
import type { CategoriaFuente } from "../../api/fuentes";
import { InputArea } from "../../components/chat/InputArea";
import { MessagesScroll } from "../../components/chat/MessagesScroll";
import { AdjuntarExpedienteModal } from "../../components/chat/AdjuntarExpedienteModal";
import { SeleccionarObrasModal } from "../../components/chat/SeleccionarObrasModal";
import { AccionesRapidas } from "../../components/chat/AccionesRapidas";
import { useSidebar } from "../../components/chat/ChatSidebarContext";
import { NOMBRE_SISTEMA } from "../../config/sistema";
import type { ExpedienteResumen } from "../../api/expedientes";
import { toast } from "../../lib/toasts";
import ConfirmDialog from "../../components/ConfirmDialog";

import styles from "./Asistente.module.css";

type Estado =
  { tipo: "idle" } | { tipo: "cargando" } | { tipo: "error"; mensaje: string };

/**
 * F3: distingue un corte de RED de un error de NEGOCIO. responderConsulta
 * (api/consultas.ts) solo adjunta `.response` cuando el fetch llegó a tener
 * una respuesta HTTP (status != 201) — un error de negocio real del
 * backend. Si `fetch()` ni siquiera pudo conectar, o la conexión se cortó a
 * mitad de `stream.read()`, lo que llega es un Error/TypeError nativo, sin
 * `.response`: eso es lo que tratamos como corte de red, recuperable.
 */
function esErrorDeRed(err: unknown): boolean {
  return !(typeof err === "object" && err !== null && "response" in err);
}

/** F1/F2: estado del stream en curso de UN chat — clave del mapa es el
 *  chatId, nunca global, para que un chat no pise la vista/estado de otro
 *  (F1) ni su cancelación dependa de lo que se envíe en otro chat (F2). */
interface StreamEnCurso {
  /** F2: contador de intento POR CHAT — reemplaza al envioRef global.
   *  Enviar de nuevo en ESTE chat lo incrementa (cancela el intento
   *  anterior de este mismo chat); enviar en OTRO chat no lo toca. */
  envioId: number;
  /** Id del mensaje bot que este stream está escribiendo (para overlay). */
  botMensajeId: string;
  /** Texto acumulado hasta ahora (fuente de verdad mientras no se persiste). */
  contenidoAcumulado: string;
}

export default function Asistente() {
  const { auth } = useAuth();
  const { puede } = usePermisos();
  const { historialAbierto, toggleHistorial, cerrarHistorial } = useSidebar();
  const usuarioId = auth.id ?? 0;

  const [conversaciones, setConversaciones] = useState<Conversacion[]>([]);
  const [espacios, setEspacios] = useState<EspacioTrabajo[]>([]);
  const [activaId, setActivaId] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [adjuntarAbierto, setAdjuntarAbierto] = useState(false);
  const [confirmarDesvincular, setConfirmarDesvincular] = useState(false);
  const [porQuitarHistorial, setPorQuitarHistorial] = useState<Mensaje | null>(
    null,
  );
  const [selectorObrasAbierto, setSelectorObrasAbierto] = useState(false);
  const [fuentesAbierta, setFuentesAbierta] = useState<CategoriaFuente | null>(
    null,
  );
  const [entrada, setEntrada] = useState("");
  const [estado, setEstado] = useState<Estado>({ tipo: "idle" });
  const [obrasExpediente, setObrasExpediente] = useState<number>(0);
  const [requisitosFaltantes, setRequisitosFaltantes] = useState<
    string[] | null
  >(null);
  const [guardandoBorrador, setGuardandoBorrador] = useState(false);
  /** Id del mensaje bot en streaming: mientras es null y `cargando` se muestra
   *  la burbuja "Valnor está analizando…" con gradiente; al crearse el mensaje
   *  bot, la burbuja se reemplaza por la escritura en vivo. */
  const [mensajeEscrituraId, setMensajeEscrituraId] = useState<string | null>(
    null,
  );

  // Abrir una conversacion pasada por URL (?chat=<id>) — p.ej. desde la
  // pagina Conversaciones ("Ver").
  const [searchParams] = useSearchParams();
  const chatParam = searchParams.get("chat");
  useEffect(() => {
    if (chatParam && usuarioId !== 0) {
      setActivaId(chatParam);
      setEstado({ tipo: "idle" });
    }
  }, [chatParam, usuarioId]);

  const montadoRef = useRef(true);
  useEffect(() => {
    montadoRef.current = true;
    return () => {
      montadoRef.current = false;
    };
  }, []);

  // F1: stream en curso POR CHAT (antes era un único mensajeEscrituraId/
  // mensajes global, así que el chat que generaba pisaba la vista de
  // cualquier otro que estuvieras mirando). streamsRef es la fuente de
  // verdad del contenido en vivo; chatsGenerando solo dispara el indicador
  // del sidebar (necesita ser estado de React para re-renderizar ChatItem).
  const streamsRef = useRef<Map<string, StreamEnCurso>>(new Map());
  // Persistencias en BD en vuelo por chat: hasta que asociarMensajeBd corre,
  // el mensaje local no tiene mensaje_id_bd y la hidratación lo duplicaría.
  const persistenciasRef = useRef<Map<string, number>>(new Map());
  const [chatsGenerando, setChatsGenerando] = useState<Set<string>>(new Set());
  // Referencia viva de activaId: el loop de enviar() es un closure de larga
  // duración y necesita saber, en cada token, si SIGUE siendo el chat que
  // se está mirando — `activaId` (el state) queda congelado en el closure.
  const activaIdRef = useRef<string | null>(null);
  useEffect(() => {
    activaIdRef.current = activaId;
  }, [activaId]);

  const marcarGenerando = useCallback((chatId: string, activo: boolean) => {
    setChatsGenerando((prev) => {
      if (prev.has(chatId) === activo) return prev;
      const next = new Set(prev);
      if (activo) next.add(chatId);
      else next.delete(chatId);
      return next;
    });
  }, []);

  const persistirYAsociar = useCallback(
    async (
      chatId: string,
      mensajeId: string,
      tipo: "user" | "bot",
      contenido: string,
    ) => {
      const pendientes = persistenciasRef.current;
      pendientes.set(chatId, (pendientes.get(chatId) ?? 0) + 1);
      try {
        const mensajeIdBd = await persistirMensajeEnChat(
          usuarioId,
          chatId,
          tipo,
          contenido,
        );
        if (mensajeIdBd !== null) {
          chatStore.asociarMensajeBd(usuarioId, mensajeId, mensajeIdBd);
        }
      } finally {
        const restantes = (pendientes.get(chatId) ?? 1) - 1;
        if (restantes > 0) pendientes.set(chatId, restantes);
        else pendientes.delete(chatId);
      }
    },
    [usuarioId],
  );

  // Mensajes del chat + el contenido en vivo de su stream (si hay uno)
  // superpuesto sobre el mensaje bot correspondiente. Única fuente para
  // pintar `mensajes`: así un chat con stream activo siempre se ve al día,
  // esté generando o recién se haya vuelto a abrir.
  const mensajesConOverlay = useCallback(
    (chatId: string): Mensaje[] => {
      const base = chatStore.listarMensajes(usuarioId, chatId);
      const live = streamsRef.current.get(chatId);
      if (!live || !live.botMensajeId) return base;
      const idx = base.findIndex((m) => m.id === live.botMensajeId);
      if (idx === -1) return base;
      const copia = [...base];
      copia[idx] = { ...copia[idx], contenido: live.contenidoAcumulado };
      return copia;
    },
    [usuarioId],
  );

  // P1: rellena el bot existente con el parcial que llega mientras se
  // pollea (nunca crea uno nuevo — eso queda solo para la resolución final,
  // ver F4). Devuelve si repintó la vista (chat visible en este momento).
  const rellenarParcialSiVisible = useCallback(
    (chatId: string, mensajeId: string, texto: string) => {
      if (!montadoRef.current) return;
      chatStore.actualizarMensaje(usuarioId, mensajeId, texto);
      if (activaIdRef.current === chatId) {
        setMensajes(mensajesConOverlay(chatId));
      }
    },
    [usuarioId, mensajesConOverlay],
  );

  // F3: recuperación tras un corte de red — mismo mecanismo que la
  // reanudación por recarga (streamResume.esperarRespuestaFinal: poll con
  // backoff a GET /consultas/historial/{id}), pero SIN recargar la página.
  // `mensajeAReponer` es el mensaje bot que ya existía (con el parcial
  // acumulado, si algo llegó a generarse) — se RELLENA, nunca se crea uno
  // nuevo (evita la burbuja duplicada de F4).
  const recuperarTrasCorte = useCallback(
    (chatId: string, historialId: number, mensajeAReponer: Mensaje | null) => {
      // P1: mientras se recupera, mostrar el parcial en vivo (throttled
      // desde el backend) en la MISMA burbuja — "verlo escribirse" también
      // en el camino de corte de red, no solo mientras el stream local vive.
      const onParcial = mensajeAReponer
        ? (texto: string) =>
            rellenarParcialSiVisible(chatId, mensajeAReponer.id, texto)
        : undefined;
      esperarRespuestaFinal(historialId, undefined, onParcial).then((res) => {
        if ("respuesta" in res) {
          if (mensajeAReponer) {
            chatStore.actualizarMensaje(
              usuarioId,
              mensajeAReponer.id,
              res.respuesta,
            );
          } else {
            chatStore.agregarMensaje(usuarioId, chatId, "bot", res.respuesta, {
              historial_id: historialId,
            });
          }
          if (montadoRef.current && activaIdRef.current === chatId) {
            setMensajes(mensajesConOverlay(chatId));
            setEstado({ tipo: "idle" });
          }
          toast(
            "Conexión recuperada: la respuesta ya está completa.",
            "success",
          );
        } else if (montadoRef.current && activaIdRef.current === chatId) {
          setEstado({ tipo: "error", mensaje: res.error });
        }
        limpiarPendiente(historialId);
      });
    },
    [usuarioId, mensajesConOverlay, rellenarParcialSiVisible],
  );

  const recargarTodo = useCallback(() => {
    if (usuarioId === 0) {
      setConversaciones([]);
      setEspacios([]);
      return;
    }
    setConversaciones(chatStore.listarConversaciones(usuarioId));
    setEspacios(chatStore.listarEspacios(usuarioId));
  }, [usuarioId]);

  useEffect(() => {
    recargarTodo();
  }, [recargarTodo]);

  // Reanudar stream interrumpido por recarga: el backend terminó igual.
  // Va después de recargarTodo (lo usa al finalizar la reanudación).
  useEffect(() => {
    if (usuarioId === 0) return;
    const pendiente = leerPendiente();
    if (!pendiente) return;
    let cancelado = false;
    // F4: el mensaje bot ya existe desde antes de la recarga (creado
    // vacío/parcial al iniciar el envío) — se RELLENA, nunca se crea una
    // segunda burbuja para la misma respuesta.
    const existentePrevio = chatStore
      .listarMensajes(usuarioId, pendiente.chatId)
      .find(
        (m) => m.tipo === "bot" && m.historial_id === pendiente.historialId,
      );
    // P1: parcial en vivo mientras pollea — si el usuario está (o entra) a
    // este chat antes de que cierre, lo ve escribirse.
    const onParcial = existentePrevio
      ? (texto: string) =>
          rellenarParcialSiVisible(pendiente.chatId, existentePrevio.id, texto)
      : undefined;
    esperarRespuestaFinal(
      pendiente.historialId,
      () => cancelado,
      onParcial,
    ).then((res) => {
      if (cancelado || !montadoRef.current) return;
      if ("respuesta" in res) {
        const existente =
          existentePrevio ??
          chatStore
            .listarMensajes(usuarioId, pendiente.chatId)
            .find(
              (m) =>
                m.tipo === "bot" && m.historial_id === pendiente.historialId,
            );
        if (existente) {
          chatStore.actualizarMensaje(usuarioId, existente.id, res.respuesta);
        } else {
          chatStore.agregarMensaje(
            usuarioId,
            pendiente.chatId,
            "bot",
            res.respuesta,
            { historial_id: pendiente.historialId },
          );
        }
        setActivaId(pendiente.chatId);
        setMensajes(chatStore.listarMensajes(usuarioId, pendiente.chatId));
        toast("Respuesta recuperada tras la recarga.", "success");
      } else {
        toast(
          res.error === "cancelado"
            ? "Reanudación cancelada."
            : "La consulta no terminó. Reintente.",
          "error",
        );
      }
      limpiarPendiente();
      recargarTodo();
    });
    return () => {
      cancelado = true;
    };
  }, [usuarioId, recargarTodo, rellenarParcialSiVisible]);

  // F1: al entrar/cambiar de chat, mostrar sus mensajes CON el overlay del
  // stream en curso (si lo hay) — y reflejar el "cargando"/indicador de ESE
  // chat, no el del último enviar() que se haya llamado en la página.
  useEffect(() => {
    if (usuarioId === 0 || activaId === null) {
      setMensajes([]);
      setEstado({ tipo: "idle" });
      setMensajeEscrituraId(null);
      return;
    }
    setMensajes(mensajesConOverlay(activaId));
    const live = streamsRef.current.get(activaId);
    if (live) {
      setEstado({ tipo: "cargando" });
      setMensajeEscrituraId(live.botMensajeId || null);
    } else {
      setEstado({ tipo: "idle" });
      setMensajeEscrituraId(null);
    }
  }, [usuarioId, activaId, mensajesConOverlay]);

  // P2 (F5): al entrar a una conversación, reconciliar con lo persistido en
  // BD — una respuesta generada en otra pestaña/dispositivo mientras esta no
  // estaba abierta aparece acá. hidratarMensajes dedupea por mensaje_id_bd
  // (nunca pisa contenido local); solo repinta si de verdad agregó algo.
  useEffect(() => {
    if (usuarioId === 0 || activaId === null) return;
    const chatId = activaId;
    let cancelado = false;
    const ocupado = () =>
      streamsRef.current.has(chatId) ||
      (persistenciasRef.current.get(chatId) ?? 0) > 0;
    if (ocupado()) return;
    hidratarMensajes(usuarioId, chatId, ocupado).then((agregados) => {
      if (cancelado || agregados === 0) return;
      if (montadoRef.current && activaIdRef.current === chatId) {
        setMensajes(mensajesConOverlay(chatId));
      }
    });
    return () => {
      cancelado = true;
    };
  }, [usuarioId, activaId, mensajesConOverlay]);

  const conversacionActiva = useMemo(
    () => conversaciones.find((c) => c.id === activaId) ?? null,
    [conversaciones, activaId],
  );

  // Cargar cantidad de obras y faltantes del expediente adjunto.
  // El aviso de faltantes es informativo: no bloquea la conversación,
  // solo advierte que auto de vista / dictamen fallará hasta subirlos.
  useEffect(() => {
    const expedienteId = conversacionActiva?.expediente_id ?? null;
    if (expedienteId === null) {
      setObrasExpediente(0);
      setRequisitosFaltantes(null);
      return;
    }
    let cancelado = false;
    listarHistorialExpediente(expedienteId, { solo_propias: false })
      .then((resp) => {
        if (!cancelado) setObrasExpediente(resp.obras.length);
      })
      .catch(() => {
        if (!cancelado) setObrasExpediente(0);
      });
    getRequisitosFaltantes(expedienteId)
      .then((resp) => {
        if (!cancelado) {
          setRequisitosFaltantes(resp.completo ? null : resp.nombres);
        }
      })
      .catch(() => {
        if (!cancelado) setRequisitosFaltantes(null);
      });
    return () => {
      cancelado = true;
    };
  }, [conversacionActiva?.expediente_id]);

  const puedeGenerarBorrador =
    conversacionActiva !== null &&
    conversacionActiva.expediente_id !== null &&
    obrasExpediente > 0;
  const puedeGuardarBorrador = puede("borradores", "crear");

  async function quitarDelHistorial() {
    const mensaje = porQuitarHistorial;
    if (mensaje === null || usuarioId === 0) return;
    const historialId = mensaje.historial_id;
    setPorQuitarHistorial(null);
    if (typeof historialId !== "number") return;
    try {
      await eliminarHistorial(historialId);
      // El registro RAG ya no existe: el mensaje no debe seguir apuntando a
      // el (la reanudacion de stream y las fuentes pedirian un id borrado).
      chatStore.desvincularHistorial(usuarioId, mensaje.id);
      if (conversacionActiva) {
        setMensajes(chatStore.listarMensajes(usuarioId, conversacionActiva.id));
      }
      toast("Consulta quitada del historial.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo quitar del historial."), "error");
    }
  }

  async function guardarBorradorDeMensaje(mensaje: Mensaje) {
    if (usuarioId === 0 || !conversacionActiva) return;
    if (!puede("borradores", "crear")) {
      toast("Tu rol no tiene permiso para guardar borradores.", "warning");
      return;
    }
    if (conversacionActiva.expediente_id === null) {
      toast("Adjunta un expediente para guardar el borrador.", "warning");
      return;
    }
    if (obrasExpediente === 0) {
      toast(
        "El expediente necesita al menos un obrado para guardar el borrador.",
        "warning",
      );
      return;
    }
    if (!mensaje.tipo_respuesta) {
      toast("Este mensaje no genera un borrador.", "warning");
      return;
    }
    setGuardandoBorrador(true);
    try {
      // F3: el chat ya esta sincronizado a BD al enviar; solo se reusan ids.
      const borrador = await guardarBorrador({
        consulta: mensaje.contenido,
        expediente_id: conversacionActiva.expediente_id,
        tipo_respuesta: mensaje.tipo_respuesta,
        contenido: mensaje.contenido,
        fuentes: null,
        chat_id: conversacionActiva.chat_id_bd ?? null,
        mensaje_id: chatStore.mensajeIdBdDe(usuarioId, mensaje.id),
        razonamiento: mensaje.razonamiento || "",
      });
      chatStore.marcarBorradorGuardado(usuarioId, mensaje.id, borrador.id);
      setMensajes(chatStore.listarMensajes(usuarioId, conversacionActiva.id));
      toast("Borrador guardado en Mis Borradores.", "success");
    } catch (err) {
      toast(mensajeError(err, "No se pudo guardar el borrador."), "error");
    } finally {
      setGuardandoBorrador(false);
    }
  }

  function seleccionarConversacion(id: string) {
    // F1: no resetear estado/mensajeEscrituraId a mano — el efecto de
    // [usuarioId, activaId] los repone según SI ESTE chat tiene un stream
    // en curso (streamsRef), no a "idle" a ciegas.
    setActivaId(id);
  }

  function adjuntarExpediente(expediente: ExpedienteResumen) {
    setAdjuntarAbierto(false);
    if (usuarioId === 0) return;
    let chatId = activaId;
    if (chatId === null) {
      const conv = chatStore.crearConversacion(usuarioId, "Sin titulo");
      chatId = conv.id;
      setActivaId(chatId);
      recargarTodo();
    }
    chatStore.asociarExpediente(usuarioId, chatId, expediente.id);
    recargarTodo();
    // Abrir selector de obras (todas marcadas por defecto).
    setSelectorObrasAbierto(true);
    toast(
      `Expediente N° ${expediente.numero_caso} adjuntado al chat.`,
      "success",
    );
  }

  function fijarCorpusRef(ref?: string) {
    if (usuarioId === 0 || activaId === null || !ref) return;
    chatStore.asociarCorpusRef(usuarioId, activaId, ref);
    recargarTodo();
    toast(`Referencia fijada: ${ref}.`, "success");
  }

  function quitarCorpusRef(ref: string) {
    if (usuarioId === 0 || activaId === null) return;
    chatStore.quitarCorpusRef(usuarioId, activaId, ref);
    recargarTodo();
  }

  function confirmarObras(obraIds: number[] | null) {
    setSelectorObrasAbierto(false);
    if (usuarioId === 0 || activaId === null) return;
    chatStore.asociarObras(usuarioId, activaId, obraIds);
    recargarTodo();
    toast(
      obraIds === null
        ? "Se consultarán todos los obrados del expediente."
        : `Se consultarán ${obraIds.length} obrado(s) seleccionados.`,
      "success",
    );
  }

  /** Desvincula el expediente de la conversación (chip ✕). */
  function desvincularExpediente() {
    if (usuarioId === 0 || activaId === null) return;
    setConfirmarDesvincular(true);
  }

  function confirmarDesvinculacion() {
    if (usuarioId === 0 || activaId === null) return;
    chatStore.asociarExpediente(usuarioId, activaId, null);
    chatStore.asociarObras(usuarioId, activaId, null);
    setObrasExpediente(0);
    setRequisitosFaltantes(null);
    recargarTodo();
    setConfirmarDesvincular(false);
    toast("Expediente desvinculado.", "success");
  }

  const [tipoForzadoRef, setTipoForzadoRef] = useState<string | null>(null);

  function elegirConsultaRapida(texto: string, tipoForzado?: string) {
    setEntrada(texto);
    setTipoForzadoRef(tipoForzado ?? null);
  }

  function nuevaConversacion() {
    if (usuarioId === 0) return;
    const conv = chatStore.crearConversacion(usuarioId, "Sin titulo");
    recargarTodo();
    setActivaId(conv.id);
    setEntrada("");
    setTipoForzadoRef(null);
    setEstado({ tipo: "idle" });
    setMensajeEscrituraId(null);
  }

  const enviar = useCallback(async () => {
    if (usuarioId === 0) return;
    const texto = entrada.trim();
    if (texto.length < 3) return;

    let chatId = activaId;
    if (chatId === null) {
      const conv = chatStore.crearConversacion(usuarioId, "Sin titulo");
      chatId = conv.id;
      setActivaId(chatId);
      recargarTodo();
    }
    // F1: fijar el chat de ESTE envío — todo lo que sigue opera sobre
    // `chatId`, nunca sobre `activaId` en vivo (que puede cambiar si el
    // usuario navega a otro chat mientras este stream sigue en curso).
    const chatIdEnvio = chatId;
    const esVisible = () => activaIdRef.current === chatIdEnvio;

    // F2: el contador de intento vive en streamsRef, por chat — enviar en
    // OTRO chat no lo toca (antes era un envioRef global: cualquier envío,
    // en cualquier chat, cancelaba lo que estuviera en curso).
    const envioId = (streamsRef.current.get(chatIdEnvio)?.envioId ?? 0) + 1;
    streamsRef.current.set(chatIdEnvio, {
      envioId,
      botMensajeId: "",
      contenidoAcumulado: "",
    });
    marcarGenerando(chatIdEnvio, true);

    const mensajeUser = chatStore.agregarMensaje(
      usuarioId,
      chatIdEnvio,
      "user",
      texto,
    );
    if (esVisible()) {
      setMensajes(mensajesConOverlay(chatIdEnvio));
      setEstado({ tipo: "cargando" });
    }
    setEntrada("");

    let botMensaje: Mensaje | null = null;
    let contenidoAcumulado = "";
    // F2: se necesita también en el catch (fuera del try) para limpiar SOLO
    // el pendiente de este intento, nunca a ciegas (streamResume.ts).
    let historialIdActual: number | null = null;

    // F3: sincroniza el chat a BD desde el primer turno (memoria conversacional).
    // Null si la BD falla: el chat local sigue funcionando sin memoria.
    const chatIdBd = await asegurarChatPersistido(usuarioId, chatIdEnvio);
    if (chatIdBd !== null) {
      void persistirYAsociar(chatIdEnvio, mensajeUser.id, "user", texto);
    }

    // F1: limpieza común a fin normal, cancelación y error — SOLO toca el
    // estado de React (mensajeEscrituraId/estado) si `chatIdEnvio` sigue
    // siendo el chat visible; si no, no pisa lo que se esté mostrando.
    const terminarStream = (estadoFinal: Estado) => {
      // F2: si streamsRef ya tiene una entrada de OTRO envioId, es que un
      // reenvío más nuevo de este MISMO chat reemplazó a este intento — no
      // tocar su entrada ni su estado, eso lo termina él, no este intento
      // viejo. `actual` undefined (ya se limpió) sí se puede limpiar igual.
      const actual = streamsRef.current.get(chatIdEnvio);
      if (actual && actual.envioId !== envioId) return;
      streamsRef.current.delete(chatIdEnvio);
      marcarGenerando(chatIdEnvio, false);
      if (esVisible()) {
        setMensajeEscrituraId(null);
        setEstado(estadoFinal);
      }
    };

    try {
      // Streaming LLM response
      // G7: propagar expediente_id de la conversacion activa para que la
      // busqueda hibrida filtre por expediente (filtro Regla 4/5 en backend)
      // en vez de buscar en todo el corpus.
      // corpus_refs se lee fresco del store (el memo puede estar rancio
      // si se fijó desde un modal sin recargar la conversación).
      const corpusFrescos =
        chatStore
          .listarConversaciones(usuarioId)
          .find((c) => c.id === chatIdEnvio)?.corpus_refs ??
        conversacionActiva?.corpus_refs ??
        null;
      const { stream, tipoRespuesta, historialId } = await responderConsulta({
        consulta: texto,
        expediente_id: conversacionActiva?.expediente_id ?? null,
        obra_ids: conversacionActiva?.obra_ids ?? null,
        chat_id: chatIdBd,
        tipo_forzado: tipoForzadoRef,
        corpus_refs: corpusFrescos,
      });
      historialIdActual = historialId;
      setTipoForzadoRef(null);

      // Reanudación tras recarga: el backend termina aunque nos vayamos.
      if (historialId !== null) {
        guardarPendiente({
          historialId,
          chatId: chatIdEnvio,
          pregunta: texto,
          ts: Date.now(),
        });
      }
      // Create initial bot message with empty content
      botMensaje = chatStore.agregarMensaje(usuarioId, chatIdEnvio, "bot", "", {
        fragmentos: [],
        scores: [],
        latencia_ms: null,
        tipo_respuesta: tipoRespuesta,
        historial_id: historialId ?? undefined,
      });
      streamsRef.current.set(chatIdEnvio, {
        envioId,
        botMensajeId: botMensaje.id,
        contenidoAcumulado: "",
      });
      if (esVisible()) {
        setMensajeEscrituraId(botMensaje.id);
        setMensajes(mensajesConOverlay(chatIdEnvio));
      }

      // Stream tokens
      while (true) {
        if (
          !montadoRef.current ||
          streamsRef.current.get(chatIdEnvio)?.envioId !== envioId
        ) {
          stream.cancel();
          // Persistir lo acumulado aunque se cancele: si no, el mensaje bot
          // queda vacio al reingresar a la conversacion.
          if (botMensaje) {
            chatStore.actualizarMensaje(
              usuarioId,
              botMensaje.id,
              contenidoAcumulado,
            );
          }
          terminarStream({ tipo: "idle" });
          return;
        }
        const { done, value } = await stream.read();
        if (done) break;
        if (value) {
          contenidoAcumulado += value;
          streamsRef.current.set(chatIdEnvio, {
            envioId,
            botMensajeId: botMensaje.id,
            contenidoAcumulado,
          });
          // F1: solo repintar si `chatIdEnvio` sigue siendo el chat que se
          // está mirando — si no, el token queda en streamsRef (overlay) y
          // se ve al volver, pero no se filtra a la vista de otro chat.
          // P4: actualizar solo el mensaje bot sobre lo ya pintado; releer el
          // store (JSON.parse completo) en cada token trababa el hilo principal.
          if (esVisible()) {
            const botId = botMensaje.id;
            const contenido = contenidoAcumulado;
            setMensajes((prev) =>
              prev.map((m) => (m.id === botId ? { ...m, contenido } : m)),
            );
          }
        }
      }

      // Persistir el contenido final al store (el streaming solo actualiza el
      // estado local; sin esto el bot queda vacio al volver a entrar).
      if (botMensaje) {
        chatStore.actualizarMensaje(
          usuarioId,
          botMensaje.id,
          contenidoAcumulado,
        );
        // Citas RAG: se traen al terminar el stream y fallan silencioso —
        // un error de fuentes nunca debe romper el mensaje ya generado.
        const mensajeBot = botMensaje;
        if (historialId !== null) {
          obtenerFuentesConsulta(historialId)
            .then((fuentes) => {
              chatStore.asociarFuentes(
                usuarioId,
                mensajeBot.id,
                fuentes.fragmentos,
                fuentes.scores,
                historialId,
              );
              if (esVisible()) {
                setMensajes(mensajesConOverlay(chatIdEnvio));
              }
            })
            .catch(() => undefined);
        }
        if (chatIdBd !== null) {
          await persistirYAsociar(
            chatIdEnvio,
            botMensaje.id,
            "bot",
            contenidoAcumulado,
          );
        }
      }

      // Refresh conversations list
      recargarTodo();
      limpiarPendiente(historialIdActual ?? undefined);
      terminarStream({ tipo: "idle" });
    } catch (err) {
      if (
        !montadoRef.current ||
        streamsRef.current.get(chatIdEnvio)?.envioId !== envioId
      ) {
        return;
      }
      if (botMensaje && contenidoAcumulado) {
        chatStore.actualizarMensaje(
          usuarioId,
          botMensaje.id,
          contenidoAcumulado,
        );
      }
      // F3: un corte de red (sin `.response` — ver esErrorDeRed) con un
      // historial ya creado en el backend NO pierde el pendiente: el
      // backend sigue generando solo. Se recupera por el mismo camino que
      // la reanudación tras recarga, sin descartar streamResume hasta que
      // la consulta cierre (completado/error) o el usuario cancele.
      if (esErrorDeRed(err) && historialIdActual !== null) {
        terminarStream({
          tipo: "error",
          mensaje:
            "Se cortó la conexión. La respuesta se sigue generando en el servidor y se recupera sola.",
        });
        recuperarTrasCorte(chatIdEnvio, historialIdActual, botMensaje);
        return;
      }
      limpiarPendiente(historialIdActual ?? undefined);
      terminarStream({
        tipo: "error",
        mensaje: mensajeError(err, "No se pudo generar la respuesta."),
      });
    }
  }, [
    usuarioId,
    activaId,
    entrada,
    recargarTodo,
    marcarGenerando,
    mensajesConOverlay,
    recuperarTrasCorte,
    persistirYAsociar,
  ]);

  function cancelar() {
    // F2: cancela el stream del chat ACTIVO únicamente — antes envioRef
    // era global, así que cancelar podía frenar el intento de cualquier
    // chat, no necesariamente el que se estaba mirando.
    if (activaId === null) return;
    const actual = streamsRef.current.get(activaId);
    if (actual) {
      streamsRef.current.set(activaId, {
        ...actual,
        envioId: actual.envioId + 1,
      });
    }
    marcarGenerando(activaId, false);
    setMensajeEscrituraId(null);
    setEstado({ tipo: "idle" });
  }

  function renombrarConversacion(id: string, titulo: string) {
    if (usuarioId === 0) return;
    chatStore.renombrarConversacion(usuarioId, id, titulo);
    recargarTodo();
    toast("Conversación renombrada.", "success");
  }

  function eliminarConversacion(id: string) {
    if (usuarioId === 0) return;
    chatStore.eliminarConversacion(usuarioId, id);
    if (activaId === id) {
      setActivaId(null);
      setMensajes([]);
    }
    recargarTodo();
    toast("Conversación eliminada.", "success");
  }

  function archivarConversacion(id: string) {
    if (usuarioId === 0) return;
    chatStore.archivarConversacion(usuarioId, id);
    if (activaId === id) setActivaId(null);
    recargarTodo();
    toast("Conversación archivada.", "success");
  }

  function desarchivarConversacion(id: string) {
    if (usuarioId === 0) return;
    chatStore.desarchivarConversacion(usuarioId, id);
    recargarTodo();
    toast("Conversación desarchivada.", "success");
  }

  function fijarConversacion(id: string) {
    if (usuarioId === 0) return;
    chatStore.fijarConversacion(usuarioId, id);
    recargarTodo();
    toast("Conversación fijada.", "success");
  }

  function desfijarConversacion(id: string) {
    if (usuarioId === 0) return;
    chatStore.desfijarConversacion(usuarioId, id);
    recargarTodo();
    toast("Conversación desfijada.", "success");
  }

  function moverACarpeta(chatId: string, espacioId: string | null) {
    if (usuarioId === 0) return;
    chatStore.moverACarpeta(usuarioId, chatId, espacioId);
    recargarTodo();
    toast(
      espacioId
        ? "Conversación movida a la carpeta."
        : "Conversación sin carpeta.",
      "success",
    );
  }

  function crearCarpeta(nombre: string): string {
    if (usuarioId === 0) return "";
    const espacio = chatStore.crearEspacio(usuarioId, nombre);
    recargarTodo();
    toast(`Carpeta "${nombre}" creada.`, "success");
    return espacio.id;
  }

  function renombrarEspacio(id: string, nombre: string) {
    if (usuarioId === 0) return;
    chatStore.renombrarEspacio(usuarioId, id, nombre);
    recargarTodo();
    toast("Carpeta renombrada.", "success");
  }

  function eliminarEspacio(id: string) {
    if (usuarioId === 0) return;
    chatStore.eliminarEspacio(usuarioId, id);
    recargarTodo();
    toast("Carpeta eliminada.", "success");
  }

  // En móvil el historial es un drawer: se cierra al elegir/crear.
  const cerrarEnMovil = () => {
    if (window.matchMedia?.("(max-width: 768px)").matches) cerrarHistorial();
  };
  const cargando = estado.tipo === "cargando";

  return (
    <div className={styles.asistente}>
      <div className={styles.asistente__body}>
        {historialAbierto && (
          <button
            type="button"
            className={styles.asistente__backdrop}
            aria-label="Cerrar historial"
            onClick={cerrarHistorial}
          />
        )}
        {historialAbierto && (
          <ChatSidebar
            onCerrar={cerrarHistorial}
            conversaciones={conversaciones}
            espacios={espacios}
            chatsGenerando={chatsGenerando}
            conversacionActivaId={activaId}
            onSeleccionarConversacion={(id) => {
              seleccionarConversacion(id);
              cerrarEnMovil();
            }}
            onRenombrarConversacion={renombrarConversacion}
            onEliminarConversacion={eliminarConversacion}
            onArchivarConversacion={archivarConversacion}
            onDesarchivarConversacion={desarchivarConversacion}
            onFijarConversacion={fijarConversacion}
            onDesfijarConversacion={desfijarConversacion}
            onMoverACarpeta={moverACarpeta}
            onNuevaConversacion={() => {
              nuevaConversacion();
              cerrarEnMovil();
            }}
            onBuscar={(q) => chatStore.buscarConversaciones(usuarioId, q)}
            onCrearCarpeta={crearCarpeta}
            onRenombrarEspacio={renombrarEspacio}
            onEliminarEspacio={eliminarEspacio}
          />
        )}

        <section className={styles.asistente__chat}>
          <div className={styles.asistente__barra}>
            <button
              type="button"
              className={styles.asistente__historial}
              onClick={toggleHistorial}
              aria-expanded={historialAbierto}
              aria-controls="historial-chat"
            >
              <History size={16} aria-hidden="true" />
              Historial
            </button>
          </div>
          {estado.tipo === "error" && (
            <p className={styles.asistente__error} role="alert">
              {estado.mensaje}
            </p>
          )}
          <MessagesScroll
            mensajes={mensajes}
            usuarioRol={auth.rol}
            conversacion={conversacionActiva}
            puedeGenerarBorrador={puedeGenerarBorrador}
            onGuardarBorrador={guardarBorradorDeMensaje}
            guardandoBorrador={guardandoBorrador}
            onEliminarHistorial={
              puede("conversaciones", "eliminar")
                ? setPorQuitarHistorial
                : undefined
            }
            mensajeEscrituraId={mensajeEscrituraId}
            puedeGuardarBorrador={puedeGuardarBorrador}
          />
          {cargando && mensajeEscrituraId === null && (
            <div className={styles.cargando} role="status">
              <span className={styles.cargando__bar} aria-hidden="true" />
              <span>{NOMBRE_SISTEMA} está analizando tu consulta…</span>
            </div>
          )}
          {requisitosFaltantes !== null &&
            requisitosFaltantes.length > 0 &&
            conversacionActiva?.expediente_id !== null &&
            conversacionActiva?.expediente_id !== undefined && (
              <div className={styles.avisoFaltantes} role="status">
                <span className={styles.avisoFaltantes__titulo}>
                  Faltan obrados para generar auto de vista / dictamen de
                  radicatoria:
                </span>{" "}
                <span className={styles.avisoFaltantes__lista}>
                  {requisitosFaltantes.join(", ")}.
                </span>
                <span className={styles.avisoFaltantes__hint}>
                  {" "}
                  Podés consultar el expediente con normalidad; solo el borrador
                  fallará hasta subirlos.
                </span>
              </div>
            )}
          <div className={styles.adjuntos}>
            <div className={styles.chips}>
              {/* Las normas del corpus jurídico entran siempre en la búsqueda. */}
              <span
                className={styles.chipInfo}
                title="Las normas del corpus jurídico siempre se consideran en la búsqueda"
              >
                <BookOpen size={14} aria-hidden="true" />
                Corpus jurídico incluido
              </span>
              {conversacionActiva?.expediente_id !== null &&
                conversacionActiva?.expediente_id !== undefined && (
                  <span className={styles.expedienteAdjunto}>
                    <FolderOpen size={14} aria-hidden="true" />
                    Expediente adjuntado
                    <button
                      type="button"
                      className={styles.expedienteAdjunto__desvincular}
                      onClick={desvincularExpediente}
                      aria-label="Desvincular expediente"
                      title="Desvincular expediente"
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </span>
                )}
              {(conversacionActiva?.corpus_refs ?? []).map((ref) => (
                <span key={ref} className={styles.expedienteAdjunto}>
                  <IconoCategoria categoria={categoriaDeRef(ref)} />
                  {ref}
                  <button
                    type="button"
                    className={styles.expedienteAdjunto__desvincular}
                    onClick={() => quitarCorpusRef(ref)}
                    aria-label={`Quitar referencia ${ref}`}
                    title="Quitar referencia fijada"
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
            {conversacionActiva?.expediente_id !== null &&
              conversacionActiva?.expediente_id !== undefined && (
                <AccionesRapidas onElegirConsulta={elegirConsultaRapida} />
              )}
          </div>
          <InputArea
            value={entrada}
            onChange={setEntrada}
            onSend={enviar}
            onCancel={cancelar}
            onAdjuntarExpediente={() => setAdjuntarAbierto(true)}
            onAdjuntarNormas={() => setFuentesAbierta("norma")}
            onAdjuntarDoctrina={() => setFuentesAbierta("doctrina")}
            onAdjuntarJurisprudencia={() => setFuentesAbierta("jurisprudencia")}
            cargando={cargando}
            deshabilitado={usuarioId === 0}
          />
          <AdjuntarExpedienteModal
            abierto={adjuntarAbierto}
            onCerrar={() => setAdjuntarAbierto(false)}
            onSeleccionar={adjuntarExpediente}
          />
          {selectorObrasAbierto && conversacionActiva?.expediente_id && (
            <SeleccionarObrasModal
              expedienteId={conversacionActiva.expediente_id}
              inicial={conversacionActiva.obra_ids ?? null}
              onConfirmar={confirmarObras}
              onCerrar={() => setSelectorObrasAbierto(false)}
            />
          )}
          <ConfirmDialog
            open={confirmarDesvincular}
            title="Desvincular expediente"
            message="Se quitará el expediente y los obrados seleccionados de esta conversación."
            confirmLabel="Desvincular"
            danger
            onConfirm={confirmarDesvinculacion}
            onCancel={() => setConfirmarDesvincular(false)}
          />
          <ConfirmDialog
            open={porQuitarHistorial !== null}
            title="Quitar del historial"
            message="La consulta dejará de figurar en el historial de consultas. El mensaje del chat se mantiene."
            confirmLabel="Quitar"
            danger
            onConfirm={() => void quitarDelHistorial()}
            onCancel={() => setPorQuitarHistorial(null)}
          />
        </section>

        <SelectorFuentes
          abierto={fuentesAbierta !== null}
          categoria={fuentesAbierta ?? "doctrina"}
          onCerrar={() => setFuentesAbierta(null)}
          expedienteId={conversacionActiva?.expediente_id ?? null}
          onSeleccionada={fijarCorpusRef}
          fijadas={conversacionActiva?.corpus_refs ?? []}
          onDesfijar={quitarCorpusRef}
        />
      </div>
    </div>
  );
}
