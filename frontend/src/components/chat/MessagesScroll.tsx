// Contenedor con scroll automatico al fondo cada vez que cambian los mensajes.
// useRef + useEffect cleanup evita setState-after-unmount.
//
// Comportamiento tipo ChatGPT (patron del proyecto de referencia, mejorado):
// - Auto-scroll al fondo SOLO si el usuario ya estaba al fondo (no lo saca de
//   donde esta leyendo). El proyecto de referencia scrollea incondicionalmente.
// - Si el usuario sube, aparece un boton flotante para bajar rapido. Su gesto
//   (rueda o dedo) suelta el pin al instante: el auto-scroll nunca lo revierte.
// - El efecto de escritura hace crecer el texto sin cambiar `mensajes`: un
//   MutationObserver mantiene el fondo mientras el usuario siga ahí.
// - Al cambiar de conversación se vuelve al fondo (no hereda el scroll previo).

import { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";

import type { Mensaje } from "../../lib/chatTypes";

import { ChatMessage } from "./ChatMessage";

import styles from "./MessagesScroll.module.css";

interface Props {
  mensajes: Mensaje[];
  /** Rol del usuario autenticado (etiqueta del mensaje del operador). */
  usuarioRol?: string | null;
  /** La conversacion activa (para chat_id_bd / expediente_id). */
  conversacion?: {
    id: string;
    expediente_id: number | null;
    chat_id_bd?: number | null;
  } | null;
  /** True si la conversacion tiene expediente y al menos una obra. */
  puedeGenerarBorrador?: boolean;
  /** Guarda (o actualiza) el borrador del mensaje. */
  onGuardarBorrador?: (mensaje: Mensaje) => void;
  /** True mientras se guarda un borrador. */
  guardandoBorrador?: boolean;
  /** Quita la consulta RAG del mensaje del historial del usuario. */
  onEliminarHistorial?: (mensaje: Mensaje) => void;
  /** Id del mensaje bot en streaming (aplica el efecto de escritura). */
  mensajeEscrituraId?: string | null;
  /** True si el rol puede crear borradores (permiso 'borradores.crear'). */
  puedeGuardarBorrador?: boolean;
}

const UMBRAL_FONDO = 50;

/** Píxeles que le faltan a la vista para llegar al final del contenido. */
function distanciaAlFondo(el: HTMLDivElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

export function MessagesScroll({
  mensajes,
  usuarioRol,
  conversacion = null,
  puedeGenerarBorrador = false,
  onGuardarBorrador,
  guardandoBorrador = false,
  onEliminarHistorial,
  mensajeEscrituraId = null,
  puedeGuardarBorrador = true,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  // Fuente de verdad del auto-scroll: "seguir el fondo".
  const atBottomRef = useRef(true);

  // Único lugar donde cambia el pin, ref y estado juntos: sincronizarlo con un
  // useEffect deja un render de retraso y el typewriter gana la carrera.
  function fijarPegado(pegado: boolean) {
    atBottomRef.current = pegado;
    setAtBottom(pegado);
  }

  // Baja al fondo. La decisión se toma acá y no al agendar: un setTimeout ya
  // programado no puede arrastrar a quien se fue a leer más arriba.
  function bajar() {
    const el = ref.current;
    if (!el || !atBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }

  // Otra conversación: arranca al fondo aunque en la anterior se hubiera subido.
  const conversacionId = conversacion?.id ?? null;
  useEffect(() => {
    fijarPegado(true);
  }, [conversacionId]);

  // El texto crece letra a letra (typewriter) sin nuevos mensajes. El div
  // cambia entre la vista vacía y la lista: se re-engancha al cambiar.
  const hayMensajes = mensajes.length > 0;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(bajar);
    obs.observe(el, { childList: true, subtree: true, characterData: true });
    return () => obs.disconnect();
  }, [hayMensajes]);

  // Auto-scroll al fondo al recibir mensajes, solo si el usuario estaba al fondo.
  useEffect(() => {
    bajar();
    const timer = window.setTimeout(bajar, 50);
    return () => window.clearTimeout(timer);
  }, [mensajes]);

  // Posición (para el botón) e intención del usuario (para el pin). El gesto
  // hacia arriba suelta el pin de forma sincrónica, antes de que el navegador
  // mueva la posición: así ninguna mutación posterior devuelve al usuario abajo.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const alScrollear = () => fijarPegado(distanciaAlFondo(el) < UMBRAL_FONDO);
    const soltar = () => {
      if (el.scrollTop > 0) fijarPegado(false);
    };
    const alGirar = (e: WheelEvent) => {
      if (e.deltaY < 0) soltar();
    };
    let yPrevio = 0;
    const alTocar = (e: TouchEvent) => {
      yPrevio = e.touches[0]?.clientY ?? 0;
    };
    const alArrastrar = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY ?? 0;
      // El dedo baja = el contenido sube.
      if (y > yPrevio) soltar();
      yPrevio = y;
    };
    el.addEventListener("scroll", alScrollear);
    el.addEventListener("wheel", alGirar, { passive: true });
    el.addEventListener("touchstart", alTocar, { passive: true });
    el.addEventListener("touchmove", alArrastrar, { passive: true });
    return () => {
      el.removeEventListener("scroll", alScrollear);
      el.removeEventListener("wheel", alGirar);
      el.removeEventListener("touchstart", alTocar);
      el.removeEventListener("touchmove", alArrastrar);
    };
  }, []);

  function scrollAlFondo() {
    const el = ref.current;
    if (!el) return;
    try {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } catch {
      el.scrollTop = el.scrollHeight;
    }
  }

  if (mensajes.length === 0) {
    return (
      <div className={styles.wrap}>
        <div className={styles.scroll} ref={ref} data-testid="messages-scroll">
          <p className={styles.empty}>
            Inicia una nueva consulta o selecciona una conversacion del sidebar.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div
        className={styles.scroll}
        ref={ref}
        data-testid="messages-scroll"
        aria-live="polite"
        aria-relevant="additions"
        aria-busy={mensajeEscrituraId !== null}
      >
        {mensajes.map((m) => {
          return (
            <ChatMessage
              key={m.id}
              mensaje={m}
              usuarioRol={usuarioRol}
              conversacion={conversacion}
              puedeGenerarBorrador={puedeGenerarBorrador}
              onGuardarBorrador={onGuardarBorrador}
              guardandoBorrador={guardandoBorrador}
              onEliminarHistorial={onEliminarHistorial}
              escritura={mensajeEscrituraId === m.id}
              puedeGuardarBorrador={puedeGuardarBorrador}
            />
          );
        })}
      </div>
      {!atBottom && (
        <button
          type="button"
          className={styles.down}
          onClick={scrollAlFondo}
          aria-label="Desplazarse hacia abajo"
          title="Ir al último mensaje"
        >
          <ArrowDown size={18} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
