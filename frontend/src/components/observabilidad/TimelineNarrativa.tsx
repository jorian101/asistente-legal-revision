// TimelineNarrativa: línea temporal SVG del pipeline RAG.
// Cada fase = nodo + barra de progreso. Color por estado:
// - pending: gris
// - running: azul animado
// - completed: verde
// - error: rojo

import { type FasePipeline } from "../../api/observabilidad";

interface FaseInfo {
  key: FasePipeline;
  label: string;
  descripcion: string;
}

const FASES: FaseInfo[] = [
  {
    key: "entendiendo",
    label: "Entendiendo",
    descripcion: "Clasificando la consulta",
  },
  {
    key: "buscando",
    label: "Buscando",
    descripcion: "Búsqueda híbrida en corpus",
  },
  {
    key: "reordenando",
    label: "Reordenando",
    descripcion: "Reranking por relevancia",
  },
  {
    key: "expandiendo",
    label: "Expandiendo",
    descripcion: "Expansión jerárquica",
  },
  {
    key: "generando",
    label: "Generando",
    descripcion: "Generación de respuesta",
  },
];

type EstadoFase = "pending" | "running" | "completed" | "error";

interface FaseEstado {
  estado: EstadoFase;
  inicio_ms?: number;
  fin_ms?: number;
  resumen?: string;
  metadata?: Record<string, unknown>;
}

interface TimelineNarrativaProps {
  fases: Record<FasePipeline, FaseEstado>;
  consultaActiva?: number;
  onFaseClick?: (fase: FasePipeline) => void;
}

export function TimelineNarrativa({
  fases,
  consultaActiva,
  onFaseClick,
}: TimelineNarrativaProps): React.JSX.Element {
  const W = 720;
  const H = 120;
  const PAD = 40;
  const R = 16;
  const GAP = (W - PAD * 2 - R * 2 * FASES.length) / (FASES.length - 1);

  // Calcular estado general
  const algunaCorriendo = Object.values(fases).some(
    (f) => f.estado === "running",
  );
  const algunaError = Object.values(fases).some((f) => f.estado === "error");
  const todasCompletadas = Object.values(fases).every(
    (f) => f.estado === "completed",
  );

  return (
    <div className="timeline-narrativa">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="timeline-narrativa__svg"
        role="img"
        aria-label={
          algunaCorriendo
            ? "Pipeline en ejecución"
            : todasCompletadas
              ? "Pipeline completado"
              : algunaError
                ? "Pipeline con error"
                : "Pipeline esperando"
        }
      >
        {/* Línea base */}
        <line
          x1={PAD + R}
          y1={H / 2}
          x2={W - PAD - R}
          y2={H / 2}
          stroke="var(--color-border)"
          strokeWidth={3}
          strokeLinecap="round"
        />

        {/* Progreso global (barra de fondo) */}
        <line
          x1={PAD + R}
          y1={H / 2}
          x2={
            PAD +
            R +
            FASES.reduce((acc, faseInfo) => {
              const estado = fases[faseInfo.key].estado;
              return (
                acc +
                (estado === "completed" ? 1 : estado === "running" ? 0.5 : 0)
              );
            }, 0) *
              (2 * R + GAP)
          }
          y2={H / 2}
          stroke="var(--color-primary)"
          strokeWidth={3}
          strokeLinecap="round"
          opacity={0.3}
        />

        {FASES.map((faseInfo, idx) => {
          const estado = fases[faseInfo.key].estado;
          const x = PAD + R + idx * (2 * R + GAP);
          const y = H / 2;
          const esUltima = idx === FASES.length - 1;

          // Color por estado
          const colorEstado = (() => {
            switch (estado) {
              case "completed":
                return "var(--color-success)";
              case "running":
                return "var(--color-primary)";
              case "error":
                return "var(--color-error)";
              default:
                return "var(--color-border)";
            }
          })();

          return (
            <g
              key={faseInfo.key}
              className="timeline-narrativa__fase"
              onClick={() => onFaseClick?.(faseInfo.key)}
              style={{ cursor: onFaseClick ? "pointer" : "default" }}
            >
              {/* Conector entre fases */}
              {!esUltima && (
                <line
                  x1={x + R}
                  y1={y}
                  x2={x + 2 * R + GAP}
                  y2={y}
                  stroke="var(--color-border)"
                  strokeWidth={3}
                  strokeLinecap="round"
                />
              )}

              {/* Nodo de la fase */}
              <circle
                cx={x}
                cy={y}
                r={R}
                fill={
                  estado === "pending" ? "var(--color-surface)" : colorEstado
                }
                stroke={colorEstado}
                strokeWidth={estado === "pending" ? 2 : 0}
                className={
                  estado === "running"
                    ? "timeline-narrativa__nodo--running"
                    : estado === "completed"
                      ? "timeline-narrativa__nodo--completed"
                      : estado === "error"
                        ? "timeline-narrativa__nodo--error"
                        : ""
                }
              >
                {estado === "running" && (
                  <animateTransform
                    attributeName="transform"
                    type="rotate"
                    from="0 12 60"
                    to="360 12 60"
                    dur="1s"
                    repeatCount="indefinite"
                  />
                )}
              </circle>

              {/* Icono dentro del nodo */}
              {estado === "completed" && (
                <text
                  x={x}
                  y={y + 4}
                  textAnchor="middle"
                  fill="white"
                  fontSize="10"
                  fontWeight="bold"
                >
                  ✓
                </text>
              )}
              {estado === "error" && (
                <text
                  x={x}
                  y={y + 4}
                  textAnchor="middle"
                  fill="white"
                  fontSize="10"
                  fontWeight="bold"
                >
                  ✕
                </text>
              )}
              {estado === "running" && (
                <circle
                  cx={x}
                  cy={y}
                  r={R - 2}
                  fill="none"
                  stroke={colorEstado}
                  strokeWidth={2}
                  strokeDasharray="8 4"
                  className="timeline-narrativa__pulse"
                >
                  <animateTransform
                    attributeName="transform"
                    type="rotate"
                    from="0 {x} {y}"
                    to="360 {x} {y}"
                    dur="1s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}

              {/* Label */}
              <text
                x={x}
                y={y + R + 20}
                textAnchor="middle"
                fontSize="11"
                fill="var(--color-text)"
                className="timeline-narrativa__label"
              >
                {faseInfo.label}
              </text>

              {/* Descripción (tooltip visible en hover) */}
              <title>
                {faseInfo.descripcion}
                {fases[faseInfo.key].resumen &&
                  `: ${fases[faseInfo.key].resumen}`}
              </title>
            </g>
          );
        })}

        {/* Indicador de consulta activa */}
        {consultaActiva && (
          <text
            x={W / 2}
            y={PAD / 2}
            textAnchor="middle"
            fontSize="13"
            fontWeight="600"
            fill="var(--color-primary)"
            className="timeline-narrativa__consulta-badge"
          >
            Seguimiento de generación
          </text>
        )}
      </svg>

      {/* Leyenda de estados */}
      <div
        className="timeline-narrativa__legend"
        role="status"
        aria-live="polite"
      >
        <span
          className={`timeline-narrativa__legend-item ${algunaCorriendo ? "active" : ""}`}
        >
          <span className="timeline-narrativa__dot running" />
          En progreso
        </span>
        <span
          className={`timeline-narrativa__legend-item ${todasCompletadas ? "active" : ""}`}
        >
          <span className="timeline-narrativa__dot completed" />
          Completado
        </span>
        <span
          className={`timeline-narrativa__legend-item ${algunaError ? "active" : ""}`}
        >
          <span className="timeline-narrativa__dot error" />
          Error
        </span>
        <span
          className={`timeline-narrativa__legend-item ${!algunaCorriendo && !todasCompletadas && !algunaError ? "active" : ""}`}
        >
          <span className="timeline-narrativa__dot pending" />
          Pendiente
        </span>
      </div>
    </div>
  );
}
