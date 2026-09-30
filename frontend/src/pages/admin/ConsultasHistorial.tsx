// ConsultasHistorial (admin): auditoria del historial RAG.
//
// Solo admin (la ruta /admin ya exige requireRol="administrador").
// Tabla con filtros de todo tipo (usuario, expediente, tipo de respuesta,
// rango de fechas y texto en la pregunta) + Eliminar (soft delete).
// Log inmutable: sin create/update.

import { useCallback, useEffect, useState } from "react";

import {
  eliminarHistorialAdmin,
  listarHistorialAdmin,
  type HistorialAdminItemDTO,
  type PaginaHistorialAdminDTO,
} from "../../api/consultas";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import ConfirmDialog from "../../components/ConfirmDialog";
import { PageHeader, Button } from "../../components/ui";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import "./ConsultasHistorial.css";

const POR_PAGINA = 25;

const TIPO_RESPUESTA_LABEL: Record<string, string> = {
  consulta_simple: "Consulta simple",
  auto_vista_consulta: "Auto de vista — consulta",
  auto_vista_apelacion_incidental: "Auto de vista — apelación incidental",
};

interface Filtros {
  usuarioId: string;
  expedienteId: string;
  tipoRespuesta: string;
  fechaDesde: string;
  fechaHasta: string;
  texto: string;
}

const FILTROS_INICIALES: Filtros = {
  usuarioId: "",
  expedienteId: "",
  tipoRespuesta: "",
  fechaDesde: "",
  fechaHasta: "",
  texto: "",
};

function columnas(
  onEliminar: (id: number) => void,
): DataTableColumn<HistorialAdminItemDTO>[] {
  return [
    {
      key: "usuario",
      header: "Usuario",
      render: (r) => (
        <span className="ch__usuario">
          <strong>{r.usuario_nombre}</strong>
          <span className="ch__carnet">{r.usuario_carnet}</span>
        </span>
      ),
    },
    {
      key: "pregunta",
      header: "Pregunta",
      render: (r) => (
        <span className="ch__pregunta" title={r.pregunta}>
          {r.pregunta}
        </span>
      ),
    },
    {
      key: "tipo_respuesta",
      header: "Tipo",
      render: (r) =>
        r.tipo_respuesta !== null
          ? (TIPO_RESPUESTA_LABEL[r.tipo_respuesta] ?? r.tipo_respuesta)
          : "—",
    },
    {
      key: "expediente_id",
      header: "Expediente",
      render: (r) => (r.expediente_id !== null ? String(r.expediente_id) : "—"),
    },
    {
      key: "latencia_ms",
      header: "Latencia",
      render: (r) => (r.latencia_ms !== null ? `${r.latencia_ms} ms` : "—"),
    },
    {
      key: "modelo_llm",
      header: "Modelo",
      render: (r) => r.modelo_llm ?? "—",
    },
    {
      key: "created_at",
      header: "Fecha",
      render: (r) =>
        r.created_at !== null ? new Date(r.created_at).toLocaleString() : "—",
    },
    {
      key: "acciones",
      header: "",
      render: (r) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onEliminar(r.id)}
          aria-label={`Eliminar entrada #${r.id}`}
        >
          Eliminar
        </Button>
      ),
    },
  ];
}

export default function ConsultasHistorial() {
  const [data, setData] = useState<PaginaHistorialAdminDTO | null>(null);
  const [pagina, setPagina] = useState(1);
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_INICIALES);
  const [confirmEliminarId, setConfirmEliminarId] = useState<number | null>(
    null,
  );
  const [archivando, setArchivando] = useState(false);

  const recargar = useCallback(() => {
    listarHistorialAdmin({
      usuario_id: filtros.usuarioId ? Number(filtros.usuarioId) : undefined,
      expediente_id: filtros.expedienteId
        ? Number(filtros.expedienteId)
        : undefined,
      tipo_respuesta: filtros.tipoRespuesta || undefined,
      fecha_desde: filtros.fechaDesde || undefined,
      fecha_hasta: filtros.fechaHasta || undefined,
      texto: filtros.texto || undefined,
      pagina,
      por_pagina: POR_PAGINA,
    })
      .then(setData)
      .catch((err) =>
        toast(mensajeError(err, "No se pudo cargar el historial."), "error"),
      );
  }, [filtros, pagina]);

  useEffect(() => {
    recargar();
  }, [recargar]);

  function aplicarFiltros() {
    setPagina(1);
    recargar();
  }

  function limpiarFiltros() {
    setFiltros(FILTROS_INICIALES);
    setPagina(1);
  }

  async function confirmarEliminar() {
    if (confirmEliminarId === null) return;
    setArchivando(true);
    try {
      await eliminarHistorialAdmin(confirmEliminarId);
      toast("Entrada archivada.", "success");
      setConfirmEliminarId(null);
      recargar();
    } catch (err) {
      toast(mensajeError(err, "No se pudo archivar la entrada."), "error");
      setConfirmEliminarId(null);
    } finally {
      setArchivando(false);
    }
  }

  return (
    <div className="ch">
      <PageHeader
        title="Consultas RAG"
        subtitle="Auditoría del historial de consultas con filtros y archivado."
      />

      <div className="ch__filtros">
        <label className="ch__campo">
          <span className="ch__label">Usuario (id)</span>
          <input
            className="input"
            value={filtros.usuarioId}
            onChange={(e) =>
              setFiltros({ ...filtros, usuarioId: e.target.value })
            }
            inputMode="numeric"
            placeholder="ej. 29"
          />
        </label>
        <label className="ch__campo">
          <span className="ch__label">Expediente (id)</span>
          <input
            className="input"
            value={filtros.expedienteId}
            onChange={(e) =>
              setFiltros({ ...filtros, expedienteId: e.target.value })
            }
            inputMode="numeric"
            placeholder="ej. 8"
          />
        </label>
        <label className="ch__campo">
          <span className="ch__label">Tipo de respuesta</span>
          <select
            className="select"
            value={filtros.tipoRespuesta}
            onChange={(e) =>
              setFiltros({ ...filtros, tipoRespuesta: e.target.value })
            }
          >
            <option value="">Todos</option>
            {Object.entries(TIPO_RESPUESTA_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="ch__campo">
          <span className="ch__label">Desde</span>
          <input
            className="input"
            type="date"
            value={filtros.fechaDesde}
            onChange={(e) =>
              setFiltros({ ...filtros, fechaDesde: e.target.value })
            }
          />
        </label>
        <label className="ch__campo">
          <span className="ch__label">Hasta</span>
          <input
            className="input"
            type="date"
            value={filtros.fechaHasta}
            onChange={(e) =>
              setFiltros({ ...filtros, fechaHasta: e.target.value })
            }
          />
        </label>
        <label className="ch__campo ch__campo--texto">
          <span className="ch__label">Texto en la pregunta</span>
          <input
            className="input"
            value={filtros.texto}
            onChange={(e) => setFiltros({ ...filtros, texto: e.target.value })}
            placeholder="ej. radicatoria"
          />
        </label>
        <div className="ch__acciones">
          <Button onClick={aplicarFiltros}>Aplicar</Button>
          <Button variant="ghost" onClick={limpiarFiltros}>
            Limpiar
          </Button>
        </div>
      </div>

      <DataTable<HistorialAdminItemDTO>
        columns={columnas((id) => setConfirmEliminarId(id))}
        rowKey={(r) => r.id}
        rows={data?.items ?? null}
        total={data?.total ?? null}
        page={pagina}
        pageSize={POR_PAGINA}
        onPageChange={setPagina}
        emptyMessage="No hay consultas registradas."
      />

      <ConfirmDialog
        open={confirmEliminarId !== null}
        title="Archivar entrada de historial"
        message="¿Seguro que deseas archivar esta entrada? La entrada se archivará y dejará de aparecer en la lista."
        confirmLabel="Archivar entrada"
        cancelLabel="Cancelar"
        danger
        busy={archivando}
        onConfirm={() => void confirmarEliminar()}
        onCancel={() => setConfirmEliminarId(null)}
      />
    </div>
  );
}
