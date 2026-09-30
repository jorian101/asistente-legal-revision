// Admin Módulos: catálogo fijo de módulos del sistema.
//
// Fase 2 del plan permisos-crud-modulos. El catálogo se siembra por
// migración (11 módulos); el admin puede:
// - Editar metadata inline: nombre, descripción, ruta, orden.
// - Activar/desactivar un módulo (desactivado → fuera del sidebar).
// No permite crear ni eliminar módulos (catálogo fijo por diseño).

import { useCallback, useEffect, useState } from "react";

import {
  type ModuloDTO,
  actualizarModulo,
  listarModulos,
} from "../../api/permisos";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import { Button, PageHeader } from "../../components/ui";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import "./Modulos.css";

export default function Modulos() {
  const [modulos, setModulos] = useState<ModuloDTO[] | null>(null);

  const cargar = useCallback(() => {
    let cancelado = false;
    listarModulos()
      .then((data) => {
        if (!cancelado) setModulos(data);
      })
      .catch((err) => {
        if (!cancelado) {
          setModulos([]);
          toast(
            mensajeError(err, "No se pudo cargar el catálogo de módulos"),
            "error",
          );
        }
      });
    return () => {
      cancelado = true;
    };
  }, []);

  useEffect(() => cargar(), [cargar]);

  const columnas: DataTableColumn<ModuloDTO>[] = [
    {
      key: "clave",
      header: "Clave",
      render: (m) => <code className="modulos__clave">{m.clave}</code>,
    },
    {
      key: "nombre",
      header: "Nombre",
      render: (m) => (
        <EditableModulo modulo={m} campo="nombre" onSaved={cargar} />
      ),
    },
    {
      key: "descripcion",
      header: "Descripción",
      render: (m) => (
        <EditableModulo modulo={m} campo="descripcion" onSaved={cargar} />
      ),
    },
    {
      key: "ruta",
      header: "Ruta",
      render: (m) => (
        <EditableModulo modulo={m} campo="ruta" onSaved={cargar} />
      ),
    },
    {
      key: "orden",
      header: "Orden",
      render: (m) => (
        <EditableModulo modulo={m} campo="orden" onSaved={cargar} />
      ),
    },
    {
      key: "activo",
      header: "Activo",
      render: (m) => <ToggleActivo modulo={m} onSaved={cargar} />,
    },
  ];

  return (
    <div className="modulos">
      <PageHeader
        title="Módulos"
        subtitle="Módulos del sidebar y su contenido."
      />
      <DataTable
        columns={columnas}
        rows={modulos}
        rowKey={(m) => m.clave}
        searchPlaceholder="Buscar módulo..."
        emptyMessage="Sin módulos."
      />
    </div>
  );
}

// --- Edición inline de un campo de módulo ---

interface EditableModuloProps {
  modulo: ModuloDTO;
  campo: "nombre" | "descripcion" | "ruta" | "orden";
  onSaved: () => void;
}

function EditableModulo({ modulo, campo, onSaved }: EditableModuloProps) {
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState(String(modulo[campo]));
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    const nuevo = campo === "orden" ? Number(valor) : valor.trim();
    if (campo === "orden" && !Number.isFinite(nuevo)) {
      toast("El orden debe ser un número.", "warning");
      return;
    }
    setGuardando(true);
    try {
      await actualizarModulo(modulo.clave, { [campo]: nuevo });
      toast("Módulo actualizado.", "success");
      setEditando(false);
      onSaved();
    } catch (err) {
      toast(mensajeError(err, "No se pudo actualizar el módulo"), "error");
    } finally {
      setGuardando(false);
    }
  }

  if (editando) {
    return (
      <span className="modulos__edit">
        <input
          type={campo === "orden" ? "number" : "text"}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          className="input modulos__edit-input"
          aria-label={`Editar ${campo}`}
          autoFocus
        />
        <Button size="sm" loading={guardando} onClick={() => void guardar()}>
          Guardar
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={guardando}
          onClick={() => {
            setValor(String(modulo[campo]));
            setEditando(false);
          }}
        >
          Cancelar
        </Button>
      </span>
    );
  }

  return (
    <span
      className="modulos__valor"
      title={campo === "descripcion" ? valor : undefined}
    >
      <span className="modulos__valor-text">{valor || "—"}</span>
      <button
        type="button"
        className="modulos__edit-boton"
        aria-label={`Editar ${campo} de ${modulo.nombre}`}
        onClick={() => {
          setValor(String(modulo[campo]));
          setEditando(true);
        }}
      >
        ✎
      </button>
    </span>
  );
}

// --- Toggle activo/inactivo ---

function ToggleActivo({
  modulo,
  onSaved,
}: {
  modulo: ModuloDTO;
  onSaved: () => void;
}) {
  const [buscando, setBuscando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  async function toggle() {
    setBuscando(true);
    try {
      await actualizarModulo(modulo.clave, { activo: !modulo.activo });
      toast(
        modulo.activo ? "Módulo desactivado." : "Módulo activado.",
        "success",
      );
      setConfirmando(false);
      onSaved();
    } catch (err) {
      toast(
        mensajeError(err, "No se pudo cambiar el estado del módulo"),
        "error",
      );
    } finally {
      setBuscando(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={
          "modulos__toggle" + (modulo.activo ? " modulos__toggle--on" : "")
        }
        onClick={() => setConfirmando(true)}
        disabled={buscando}
        aria-pressed={modulo.activo}
      >
        {modulo.activo ? "Activo" : "Inactivo"}
      </button>
      <ConfirmDialog
        open={confirmando}
        title={modulo.activo ? "Desactivar módulo" : "Activar módulo"}
        message={
          modulo.activo ? (
            <>
              <strong>{modulo.nombre}</strong> dejará de aparecer en el menú de
              todos los usuarios.
            </>
          ) : (
            <>
              <strong>{modulo.nombre}</strong> volverá a aparecer en el menú de
              los usuarios con permiso.
            </>
          )
        }
        confirmLabel={modulo.activo ? "Desactivar" : "Activar"}
        danger={modulo.activo}
        busy={buscando}
        onConfirm={() => void toggle()}
        onCancel={() => setConfirmando(false)}
      />
    </>
  );
}
