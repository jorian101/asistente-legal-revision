// Admin Sala de Control: observabilidad del pipeline RAG en vivo (Sprint 7).
//
// Conecta via SSE a /admin/pipeline/events y muestra trazabilidad narrativa
// con timeline SVG + detalle de fases + preview de fragmentos.

import { SalaControl } from "../../components/observabilidad";

export default function SalaControlPage() {
  return <SalaControl />;
}
