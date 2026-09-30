// Admin Auditoría: log de acciones sensitivas (Trail of Bits R6).
//
// Datos: GET /admin/auditoria (api/metricas.ts). Solo admin.
// Tabla con accion, entidad, usuario, detalle y timestamp. Filtro por
// accion (login, crear_expediente, publicar_borrador, eliminar_*...).

import { useCallback, useEffect, useMemo, useState } from "react";

import { type AuditoriaItemDTO, listarAuditoria } from "../../api/metricas";

import DataTable, { type DataTableColumn } from "../../components/DataTable";

import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import { PageHeader } from "../../components/ui";

import "./Auditoria.css";

const LIMITE = 100;

const ACCION_LABEL: Record<string, string> = {
  login: "Login",
  login_fallido: "Login fallido",
  crear_expediente: "Crear expediente",
  publicar_borrador: "Publicar borrador",
  eliminar_borrador: "Eliminar borrador",
  eliminar_expediente: "Eliminar expediente",
  eliminar_norma: "Eliminar norma",
};

function accionLegible(accion: string): string {
  return ACCION_LABEL[accion] ?? accion;
}

function formatFecha(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function formatDetalle(detalle: Record<string, unknown> | null): string {
  if (!detalle) return "—";
  return Object.entries(detalle)
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(", ");
}

export default function Auditoria() {
  const [items, setItems] = useState<AuditoriaItemDTO[] | null>(null);
  const [accion, setAccion] = useState<string>("");

  const cargar = useCallback(() => {
    let cancelado = false;
    listarAuditoria(accion || undefined, LIMITE)
      .then((resp) => {
        if (!cancelado) setItems(resp.items);
      })
      .catch((err) => {
        if (!cancelado) {
          setItems([]);
          toast(mensajeError(err, "No se pudo cargar la auditoría"), "error");
        }
      });
    return () => {
      cancelado = true;
    };
  }, [accion]);

  useEffect(() => cargar(), [cargar]);

  const columnas = useMemo<DataTableColumn<AuditoriaItemDTO>[]>(
    () => [
      {
        key: "accion",
        header: "Acción",
        render: (r) => accionLegible(r.accion),
      },
      {
        key: "entidad",
        header: "Entidad",
        render: (r) =>
          r.entidad ? `${r.entidad} #${r.entidad_id ?? ""}` : "—",
      },
      { key: "usuario_id", header: "Usuario" },
      {
        key: "detalle",
        header: "Detalle",
        render: (r) => formatDetalle(r.detalle),
      },
      {
        key: "created_at",
        header: "Fecha",
        render: (r) => formatFecha(r.created_at),
      },
    ],
    [],
  );

  return (
    <div className="auditoria">
      <PageHeader
        title="Auditoría"
        subtitle="Trail of Bits R6 — trazabilidad de acciones sensitivas."
      />

      <DataTable
        columns={columnas}
        rows={items}
        rowKey={(r) => `${r.accion}-${r.created_at}-${r.entidad_id ?? ""}`}
        searchPlaceholder="Buscar en auditoría..."
        emptyMessage="Sin registros de auditoría."
        filtros={
          <select
            className="select"
            value={accion}
            onChange={(e) => setAccion(e.target.value)}
            aria-label="Filtrar por acción"
          >
            <option value="">Todas las acciones</option>
            {Object.keys(ACCION_LABEL).map((a) => (
              <option key={a} value={a}>
                {ACCION_LABEL[a]}
              </option>
            ))}
          </select>
        }
        total={items?.length ?? null}
      />
    </div>
  );
}
