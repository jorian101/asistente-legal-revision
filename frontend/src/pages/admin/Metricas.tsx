// Admin Dashboard: resumen general del sistema del asistente.
//
// Datos: GET /admin/dashboard/resumen (api/metricas.ts) — KPIs de chats,
// uso por modelo LLM (cantidad + latencia media), por tipo, por usuario y
// por dia, mas el modelo activo (LLM + embeddings) de configuracion_rag.
//
// Graficos con SVG nativo (sin libreria de charts). Solo admin.

import { useEffect, useMemo, useState } from "react";

import {
  type DashboardResumenDTO,
  type EndpointActivoDTO,
  type MetricasSaludDTO,
  obtenerResumenDashboard,
  obtenerSaludSistema,
} from "../../api/metricas";

import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { PageHeader, StateMessage } from "../../components/ui";

import "./Metricas.css";

const TIPO_LABEL: Record<string, string> = {
  consulta_simple: "Consulta simple",
  auto_vista_consulta: "Auto de vista — consulta",
  auto_vista_apelacion_incidental: "Auto de vista — apelación incidental",
  dictamen_radicatoria_consulta: "Dictamen — consulta",
  dictamen_radicatoria_apelacion: "Dictamen — apelación",
};

function tipoLabel(t: string): string {
  return TIPO_LABEL[t] ?? t.replace(/_/g, " ");
}

function formatMs(ms: number | null): string {
  if (ms === null || Number.isNaN(ms)) return "—";
  return `${Math.round(ms)} ms`;
}

const PROVIDER_LABEL: Record<string, string> = {
  ollama: "Ollama (local)",
  http: "HTTP (local)",
};

/** Card de un endpoint activo: qué modelo es y dónde corre. */
function ModeloCard({
  label,
  endpoint,
}: {
  label: string;
  endpoint: EndpointActivoDTO | null;
}) {
  return (
    <div className="metricas__modelo-card metricas__modelo-card--readonly">
      <span className="metricas__modelo-label">{label}</span>
      <span className="metricas__modelo-value">
        {endpoint?.model ?? "No configurado"}
      </span>
      {endpoint && (
        <span className="metricas__modelo-badge">
          {PROVIDER_LABEL[endpoint.provider] ?? endpoint.provider}
        </span>
      )}
    </div>
  );
}

/** Formato corto de fecha: "15 mar" */
function fechaCorto(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const MES = [
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
  ];
  return `${d.getDate()} ${MES[d.getMonth()]}`;
}

// ----- SVG: bar chart de consultas por día (mejorado) -----

function DiaChart({
  items,
}: {
  items: DashboardResumenDTO["consultas_por_dia"];
}) {
  const W = 720;
  const H = 200;
  const PAD_TOP = 24;
  const PAD_BOTTOM = 36;
  const PAD_LEFT = 40;
  const PAD_RIGHT = 16;
  const usableW = W - PAD_LEFT - PAD_RIGHT;
  const usableH = H - PAD_TOP - PAD_BOTTOM;
  const max = Math.max(1, ...items.map((i) => i.cantidad));
  const barW = items.length > 0 ? usableW / items.length : 0;

  // Etiquetas del eje Y (0, max/2, max)
  const ticksY = [0, Math.round(max / 2), max];

  return (
    <svg
      className="metricas__chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Consultas por día (últimos 14 días)"
    >
      {/* Gridlines horizontales */}
      {ticksY.map((tick) => {
        const y = PAD_TOP + usableH - (tick / max) * usableH;
        return (
          <g key={`tick-${tick}`}>
            <line
              x1={PAD_LEFT}
              y1={y}
              x2={W - PAD_RIGHT}
              y2={y}
              stroke="var(--color-border)"
              strokeWidth={0.5}
              strokeDasharray="4,4"
            />
            <text
              x={PAD_LEFT - 8}
              y={y + 4}
              textAnchor="end"
              fontSize={10}
              fill="var(--color-text-muted)"
            >
              {tick}
            </text>
          </g>
        );
      })}

      {/* Barras + etiquetas */}
      {items.map((i, idx) => {
        const h = (i.cantidad / max) * usableH;
        const x = PAD_LEFT + idx * barW + barW * 0.15;
        const barWFinal = barW * 0.7;
        const y = PAD_TOP + usableH - h;
        return (
          <g key={i.fecha}>
            <rect
              x={x}
              y={y}
              width={barWFinal}
              height={Math.max(h, 1)}
              rx={3}
              fill="var(--color-primary)"
            >
              <title>
                {i.fecha}: {i.cantidad} consulta(s)
              </title>
            </rect>
            {/* Valor sobre la barra */}
            {i.cantidad > 0 && (
              <text
                x={x + barWFinal / 2}
                y={y - 6}
                textAnchor="middle"
                fontSize={11}
                fontWeight={600}
                fill="var(--color-text-strong)"
              >
                {i.cantidad}
              </text>
            )}
            {/* Fecha debajo */}
            <text
              x={x + barWFinal / 2}
              y={H - PAD_BOTTOM + 16}
              textAnchor="middle"
              fontSize={9}
              fill="var(--color-text-muted)"
            >
              {fechaCorto(i.fecha)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ----- Página -----

export default function Dashboard() {
  const [resumen, setResumen] = useState<DashboardResumenDTO | null>(null);
  const [saludInfra, setSaludInfra] = useState<MetricasSaludDTO | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let cancelado = false;
    setCargando(true);
    obtenerResumenDashboard()
      .then((r) => {
        if (!cancelado) setResumen(r);
      })
      .catch((err) => {
        if (!cancelado)
          toast(mensajeError(err, "No se pudieron cargar los datos."), "error");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });
    // Salud de infraestructura: falla silenciosa (sección se oculta).
    obtenerSaludSistema()
      .then((s) => {
        if (!cancelado) setSaludInfra(s);
      })
      .catch(() => {
        if (!cancelado) setSaludInfra(null);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const salud = useMemo(() => {
    if (!resumen || resumen.total_consultas === 0) return null;
    const total = resumen.total_consultas;
    const errPct = (resumen.con_error / total) * 100;
    const okPct = (resumen.completadas / total) * 100;
    const progPct = (resumen.en_progreso / total) * 100;
    return { errPct, okPct, progPct, total };
  }, [resumen]);

  return (
    <div className="metricas">
      <PageHeader
        title="Dashboard"
        subtitle="Resumen general del asistente: uso, modelos y salud del sistema."
      />

      {cargando && (
        <StateMessage tipo="cargando">Cargando dashboard…</StateMessage>
      )}
      {!cargando && resumen === null && (
        <StateMessage tipo="error">
          No se pudieron cargar los datos.
        </StateMessage>
      )}

      {resumen !== null && (
        <>
          {/* ── Resumen general ── */}
          <div className="metricas__cards">
            <div className="metricas__card">
              <span className="metricas__card-value">
                {resumen.total_consultas}
              </span>
              <span className="metricas__card-label">Consultas totales</span>
            </div>
            <div className="metricas__card">
              <span className="metricas__card-value">
                {resumen.completadas}
              </span>
              <span className="metricas__card-label">Completadas</span>
            </div>
            <div
              className={
                "metricas__card" +
                (resumen.con_error > 0 ? " metricas__card--alert" : "")
              }
            >
              <span className="metricas__card-value">{resumen.con_error}</span>
              <span className="metricas__card-label">Con error</span>
            </div>
            <div
              className={
                "metricas__card" +
                (resumen.en_progreso > 0 ? " metricas__card--working" : "")
              }
            >
              <span className="metricas__card-value">
                {resumen.en_progreso}
              </span>
              <span className="metricas__card-label">En progreso</span>
            </div>
          </div>

          {/* ── Barra de salud ── */}
          {salud !== null && (
            <section className="metricas__chartblock">
              <h2 className="metricas__section">Salud del sistema</h2>
              <div className="metricas__salud">
                <div className="metricas__salud-bar">
                  <div
                    className="metricas__salud-seg metricas__salud-seg--ok"
                    style={{ width: `${salud.okPct}%` }}
                    title={`${resumen.completadas} completadas`}
                  />
                  {salud.progPct > 0 && (
                    <div
                      className="metricas__salud-seg metricas__salud-seg--prog"
                      style={{ width: `${salud.progPct}%` }}
                      title={`${resumen.en_progreso} en progreso`}
                    />
                  )}
                  {salud.errPct > 0 && (
                    <div
                      className="metricas__salud-seg metricas__salud-seg--err"
                      style={{ width: `${salud.errPct}%` }}
                      title={`${resumen.con_error} con error`}
                    />
                  )}
                </div>
                <div className="metricas__salud-legend">
                  <span className="metricas__legend-item metricas__legend-item--ok">
                    {Math.round(salud.okPct)}% completadas
                  </span>
                  {salud.progPct > 0 && (
                    <span className="metricas__legend-item metricas__legend-item--prog">
                      {Math.round(salud.progPct)}% en progreso
                    </span>
                  )}
                  {salud.errPct > 0 && (
                    <span className="metricas__legend-item metricas__legend-item--err">
                      {Math.round(salud.errPct)}% con error
                    </span>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* ── Infraestructura (HU-22) ── */}
          {saludInfra !== null && (
            <section className="metricas__chartblock">
              <h2 className="metricas__section">Infraestructura</h2>
              <div className="metricas__infra">
                <div className="metricas__modelo-card">
                  <span className="metricas__modelo-label">
                    <span
                      className={
                        "metricas__estado-dot " +
                        (saludInfra.postgres_ok
                          ? "metricas__estado-dot--ok"
                          : "metricas__estado-dot--err")
                      }
                    />
                    PostgreSQL
                  </span>
                  <span className="metricas__modelo-value">
                    {saludInfra.postgres_ok ? "Operativo" : "Caído"}
                  </span>
                </div>
                <div className="metricas__modelo-card">
                  <span className="metricas__modelo-label">
                    <span
                      className={
                        "metricas__estado-dot " +
                        (saludInfra.qdrant_ok
                          ? "metricas__estado-dot--ok"
                          : "metricas__estado-dot--err")
                      }
                    />
                    Qdrant (corpus jurídico)
                  </span>
                  <span className="metricas__modelo-value">
                    {saludInfra.qdrant_ok
                      ? `${saludInfra.qdrant_puntos.toLocaleString("es")} puntos`
                      : "Caído"}
                  </span>
                </div>
                <div className="metricas__modelo-card">
                  <span className="metricas__modelo-label">
                    Sesiones activas
                  </span>
                  <span className="metricas__modelo-value">
                    {saludInfra.sesiones_activas}
                  </span>
                  <span className="metricas__modelo-badge">
                    Sala de Control
                  </span>
                </div>
              </div>
            </section>
          )}

          {/* ── Uso en el tiempo ── */}
          <section className="metricas__chartblock">
            <h2 className="metricas__section">Consultas por día</h2>
            {resumen.consultas_por_dia.length === 0 ? (
              <StateMessage tipo="vacio">
                Sin consultas en el período.
              </StateMessage>
            ) : (
              <DiaChart items={resumen.consultas_por_dia} />
            )}
          </section>

          {/* ── Configuración de modelos (endpoints activos) ── */}
          <section className="metricas__chartblock">
            <h2 className="metricas__section">Configuración de modelos</h2>
            <div className="metricas__modelos">
              <ModeloCard
                label="LLM (generación)"
                endpoint={resumen.llm_endpoint}
              />
              <ModeloCard
                label="Embeddings"
                endpoint={resumen.embedding_endpoint}
              />
              <ModeloCard
                label="Reranker"
                endpoint={resumen.reranker_endpoint}
              />
            </div>
          </section>

          {/* ── Distribución: por modelo + por tipo ── */}
          {(resumen.por_modelo.length > 0 || resumen.por_tipo.length > 0) && (
            <section className="metricas__chartblock">
              <h2 className="metricas__section">Distribución de uso</h2>

              {/* Por modelo */}
              {resumen.por_modelo.length > 0 ? (
                <div className="metricas__lista">
                  {resumen.por_modelo.map((m) => (
                    <div
                      key={m.modelo_llm ?? "sin_modelo"}
                      className="metricas__lista-item"
                    >
                      <span className="metricas__lista-label">
                        {m.modelo_llm ?? "Sin modelo"}
                      </span>
                      <span className="metricas__lista-meta">
                        {m.cantidad} consulta(s) · latencia media{" "}
                        {formatMs(m.latencia_promedio_ms)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <StateMessage tipo="vacio">
                  Sin datos de uso por modelo.
                </StateMessage>
              )}

              {/* Por tipo */}
              {resumen.por_tipo.length > 0 && (
                <div className="metricas__tipos">
                  {resumen.por_tipo.map((t) => (
                    <span key={t.tipo_respuesta} className="metricas__tipo">
                      {tipoLabel(t.tipo_respuesta)} · {t.cantidad}
                    </span>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* ── Adopción por usuario ── */}
          <section className="metricas__chartblock">
            <h2 className="metricas__section">Consultas por usuario</h2>
            {resumen.por_usuario.length === 0 ? (
              <StateMessage tipo="vacio">
                Sin usuarios con consultas.
              </StateMessage>
            ) : (
              <ul className="metricas__usuarios">
                {resumen.por_usuario.map((u) => (
                  <li key={u.usuario_id} className="metricas__usuario">
                    <span>
                      {u.usuario_nombre} ({u.usuario_carnet})
                    </span>
                    <span className="metricas__usuario-count">
                      {u.cantidad} consulta(s)
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
