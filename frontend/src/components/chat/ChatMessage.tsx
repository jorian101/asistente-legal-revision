// Burbuja de mensaje del chat. Renderiza user y bot con la misma composicion:
// user = consulta, bot = "respuesta" + fragmentos RAG.

import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import {
  Bot,
  User,
  ThumbsUp,
  ThumbsDown,
  Copy,
  Check,
  Save,
  RefreshCw,
  Trash2,
} from "lucide-react";

import type { FragmentoCita, Mensaje } from "../../lib/chatTypes";
import { etiquetaFuente, resumenFuentes } from "../../lib/fuentesLabel";
import { getFeedback, setFeedback, clearFeedback } from "../../lib/feedback";
import { NOMBRE_SISTEMA } from "../../config/sistema";
import { labelRol } from "../../config/modulosPorRol";

import styles from "./ChatMessage.module.css";

// Convierte markdown a HTML y lo sanitiza. El contenido proviene del LLM y
// puede incluir HTML/JS peligroso, por eso DOMPurify antes de inyectarlo.
function renderMarkdown(contenido: string): string {
  const html = marked.parse(contenido, { gfm: true, breaks: true });
  return DOMPurify.sanitize(html as string);
}

/** Efecto de escritura: revela `texto` progresivamente a velocidad limitada.
 *
 * Si el stream llega lento, se mantiene al día (nunca se atrasa del texto
 * acumulado); si el modelo genera de golpe (rápido), lo "escribe" a
 * `charsPorSeg` — el asistente se ve tipeando aunque la respuesta haya
 * llegado completa. Solo se aplica al mensaje bot en streaming.
 */
const INTERVALO_RENDER_MS = 100;

function useTypewriter(texto: string, charsPorSeg = 480): string {
  const [mostrado, setMostrado] = useState(0);
  const mostradoRef = useRef(0);
  const rafRef = useRef(0);

  useEffect(() => {
    if (texto.length === 0) {
      mostradoRef.current = 0;
      setMostrado(0);
      return;
    }
    mostradoRef.current = Math.min(mostradoRef.current, texto.length);
    if (mostradoRef.current >= texto.length) {
      setMostrado(texto.length);
      return;
    }
    let anterior = performance.now();
    let ultimoRender = 0;
    const loop = (ahora: number) => {
      const delta = ((ahora - anterior) / 1000) * charsPorSeg;
      anterior = ahora;
      mostradoRef.current = Math.min(
        texto.length,
        mostradoRef.current + Math.max(1, delta),
      );
      // Cada render re-parsea y sanitiza TODO el markdown: a ~10 Hz el efecto
      // se ve igual de fluido y el costo deja de crecer por frame.
      const fin = mostradoRef.current >= texto.length;
      if (fin || ahora - ultimoRender >= INTERVALO_RENDER_MS) {
        ultimoRender = ahora;
        setMostrado(mostradoRef.current);
      }
      if (mostradoRef.current < texto.length) {
        rafRef.current = requestAnimationFrame(loop);
      }
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [texto, charsPorSeg]);

  return texto.slice(0, mostrado);
}

// Tipos de respuesta que producen borrador (auto_vista_* / dictamen_*).
// auto_vista_apelacion_restringida se agrega cuando el backend lo soporte
// (hoy el clasificador solo emite incidental).
const TIPOS_BORRADOR = new Set([
  "auto_vista_consulta",
  "auto_vista_apelacion_incidental",
  "dictamen_radicatoria_consulta",
  "dictamen_radicatoria_apelacion",
]);

interface Props {
  mensaje: Mensaje;
  /** Rol del usuario autenticado, para etiquetar el mensaje del operador. */
  usuarioRol?: string | null;
  /** La conversacion activa (para chat_id_bd / expediente_id). */
  conversacion?: {
    id: string;
    expediente_id: number | null;
    chat_id_bd?: number | null;
  } | null;
  /** True si la conversacion tiene expediente y al menos una obra. */
  puedeGenerarBorrador?: boolean;
  /** Guarda (o actualiza) el borrador de este mensaje. */
  onGuardarBorrador?: (mensaje: Mensaje) => void;
  /** True mientras se esta guardando el borrador. */
  guardandoBorrador?: boolean;
  /** Quita la consulta RAG de este mensaje del historial del usuario. */
  onEliminarHistorial?: (mensaje: Mensaje) => void;
  /** True si este mensaje bot esta en streaming (aplica efecto de escritura). */
  escritura?: boolean;
  /** True si el rol puede crear borradores (permiso 'borradores.crear'). */
  puedeGuardarBorrador?: boolean;
}

function FragmentoItem({ fragmento }: { fragmento: FragmentoCita }) {
  const [expandido, setExpandido] = useState(false);

  // Etiqueta + referencia legibles: lógica pura en ../../lib/fuentesLabel.
  const { badge, categoria, etiqueta } = etiquetaFuente(fragmento);

  const textoLargo = fragmento.texto.length > 320;

  return (
    <li className={styles.fragmento}>
      <div className={styles.fragmento__header}>
        <span
          className={
            styles.fragmento__badge +
            (categoria === "norma"
              ? ""
              : ` ${styles[`fragmento__badge--${categoria === "doctrina" || categoria === "jurisprudencia" ? categoria : "obra"}`]}`)
          }
        >
          {badge}
        </span>
        {etiqueta !== null && (
          <span className={styles.fragmento__ref}>{etiqueta}</span>
        )}
      </div>

      <p className={expandido ? undefined : styles.fragmento__texto_clamp}>
        {fragmento.texto}
      </p>
      {textoLargo && (
        <button
          type="button"
          className={styles.fragmento__vermas}
          aria-expanded={expandido}
          onClick={() => setExpandido((v) => !v)}
        >
          {expandido ? "Ver menos" : "Ver más"}
        </button>
      )}
    </li>
  );
}

export function ChatMessage({
  mensaje,
  usuarioRol,
  conversacion = null,
  puedeGenerarBorrador = false,
  onGuardarBorrador,
  guardandoBorrador = false,
  onEliminarHistorial,
  escritura = false,
  puedeGuardarBorrador = true,
}: Props) {
  const esBot = mensaje.tipo === "bot";
  const clase = `${styles.bubble} ${esBot ? styles["bubble--bot"] : styles["bubble--user"]}`;
  const revelado = useTypewriter(esBot && escritura ? mensaje.contenido : "");
  const contenidoVisible = esBot && escritura ? revelado : mensaje.contenido;
  const htmlBot = useMemo(
    () => (esBot ? renderMarkdown(contenidoVisible) : ""),
    [esBot, contenidoVisible],
  );
  const generaBorrador =
    esBot &&
    mensaje.tipo_respuesta !== undefined &&
    mensaje.tipo_respuesta !== null &&
    TIPOS_BORRADOR.has(mensaje.tipo_respuesta);
  const yaGuardado = Boolean(mensaje.borrador_id);

  return (
    <article className={clase} data-tipo={mensaje.tipo}>
      <header className={styles.bubble__header}>
        <span className={styles.bubble__icon} aria-hidden="true">
          {esBot ? <Bot size={14} /> : <User size={14} />}
        </span>
        <span>{esBot ? NOMBRE_SISTEMA : labelRol(usuarioRol)}</span>
      </header>

      {esBot ? (
        <div
          className={styles.bubble__markdown}
          dangerouslySetInnerHTML={{ __html: htmlBot }}
        />
      ) : (
        <p className={styles.bubble__body}>{mensaje.contenido}</p>
      )}

      {esBot && (
        <div className={styles.bubble__meta}>
          {mensaje.latencia_ms !== null &&
            mensaje.latencia_ms !== undefined && (
              <span>{mensaje.latencia_ms} ms</span>
            )}
          <div className={styles.bubble__actions}>
            <CopiarRespuesta contenido={mensaje.contenido} />
            {mensaje.id && <FeedbackButtons mensajeId={mensaje.id} />}
            {onEliminarHistorial !== undefined &&
              typeof mensaje.historial_id === "number" && (
                <button
                  type="button"
                  className={styles.bubble__copy}
                  onClick={() => onEliminarHistorial(mensaje)}
                  aria-label="Quitar del historial"
                  title="Quitar del historial"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              )}
          </div>
        </div>
      )}

      {esBot && mensaje.fragmentos && mensaje.fragmentos.length > 0 && (
        <details className={styles.bubble__fuentes} open={false}>
          <summary className={styles.bubble__fuentes_toggle}>
            <span>
              Fuentes ·{" "}
              <span className={styles.bubble__fuentes_desglose}>
                {resumenFuentes(mensaje.fragmentos)}
              </span>
            </span>
            <span
              className={styles.bubble__fuentes_chevron}
              aria-hidden="true"
            />
          </summary>
          <ul className={styles.bubble__fragmentos}>
            {mensaje.fragmentos.map((f, idx) => (
              <FragmentoItem key={`${f.id ?? "s"}-${idx}`} fragmento={f} />
            ))}
          </ul>
        </details>
      )}

      {generaBorrador && puedeGuardarBorrador && (
        <BotonGuardarBorrador
          conversacion={conversacion}
          puedeGenerar={puedeGenerarBorrador}
          yaGuardado={yaGuardado}
          guardando={guardandoBorrador}
          onGuardar={() => onGuardarBorrador?.(mensaje)}
        />
      )}
    </article>
  );
}

function BotonGuardarBorrador({
  conversacion,
  puedeGenerar,
  yaGuardado,
  guardando,
  onGuardar,
}: {
  conversacion: Props["conversacion"];
  puedeGenerar: boolean;
  yaGuardado: boolean;
  guardando: boolean;
  onGuardar: () => void;
}) {
  const sinExpediente = !conversacion?.expediente_id;
  const sinObras = Boolean(!puedeGenerar && conversacion?.expediente_id);

  let titulo = "Guardar en Mis Borradores";
  if (sinExpediente) titulo = "Adjunta un expediente para guardar el borrador";
  else if (sinObras)
    titulo =
      "El expediente necesita al menos un obrado para guardar el borrador";
  else if (yaGuardado) titulo = "Actualizar mi borrador";

  const disabled = guardando || sinExpediente || sinObras;

  return (
    <button
      type="button"
      className={styles.borrador_btn}
      onClick={onGuardar}
      disabled={disabled}
      title={titulo}
      aria-label={titulo}
    >
      {yaGuardado ? (
        <RefreshCw size={14} aria-hidden="true" />
      ) : (
        <Save size={14} aria-hidden="true" />
      )}
      {guardando
        ? "Guardando..."
        : yaGuardado
          ? "Actualizar mi borrador"
          : "Guardar en Mis Borradores"}
    </button>
  );
}

function CopiarRespuesta({ contenido }: { contenido: string }) {
  const [copiado, setCopiado] = useState(false);

  async function handleCopiar() {
    try {
      await navigator.clipboard.writeText(contenido);
    } catch {
      // Fallback para contextos sin Clipboard API.
      const ta = document.createElement("textarea");
      ta.value = contenido;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 2000);
  }

  return (
    <button
      type="button"
      className={styles.bubble__copy}
      onClick={handleCopiar}
      aria-label={copiado ? "Respuesta copiada" : "Copiar respuesta"}
      title={copiado ? "Copiada" : "Copiar"}
    >
      {copiado ? (
        <Check size={14} aria-hidden="true" />
      ) : (
        <Copy size={14} aria-hidden="true" />
      )}
    </button>
  );
}

function FeedbackButtons({ mensajeId }: { mensajeId: string }) {
  // Estado local para que el boton refleje el click al instante; la fuente
  // de verdad persiste en localStorage (getFeedback/setFeedback).
  const [feedback, setFeedbackState] = useState<"like" | "dislike" | null>(() =>
    getFeedback(mensajeId),
  );

  function handleFeedback(valor: "like" | "dislike") {
    if (feedback === valor) {
      clearFeedback(mensajeId);
      setFeedbackState(null);
    } else {
      setFeedback(mensajeId, valor);
      setFeedbackState(valor);
    }
  }

  return (
    <div
      className={styles.bubble__feedback}
      role="group"
      aria-label="Valorar respuesta"
    >
      <button
        className={`${styles.bubble__feedback_btn} ${feedback === "like" ? styles.active : ""}`}
        onClick={() => handleFeedback("like")}
        aria-pressed={feedback === "like"}
        aria-label={feedback === "like" ? "Quitar like" : "Like"}
      >
        <ThumbsUp size={14} aria-hidden="true" />
      </button>
      <button
        className={`${styles.bubble__feedback_btn} ${feedback === "dislike" ? styles.active : ""}`}
        onClick={() => handleFeedback("dislike")}
        aria-pressed={feedback === "dislike"}
        aria-label={feedback === "dislike" ? "Quitar dislike" : "Dislike"}
      >
        <ThumbsDown size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
