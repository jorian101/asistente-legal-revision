// Admin Permisos de Usuario: matriz de permisos CRUD por módulo.
//
// Fase 2 del plan permisos-crud-modulos. Para cada usuario (no admin) el
// admin puede:
// - Ver el permiso EFECTIVO (default del rol ⊕ override).
// - Anular con un override por celda: Default (seguir rol) / Permitir / Denegar.
// Los usuarios administradores no se pueden modificar (regla de seguridad:
// admin siempre full) y aparecen deshabilitados en el selector.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useBlocker } from "react-router-dom";

import {
  type PermisoModuloDetalleDTO,
  type PermisoOverrideDTO,
  asignarPermisosUsuario,
  listarPermisosUsuario,
  listarUsuarios,
  type UsuarioPermisosDTO,
} from "../../api/permisos";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import {
  Button,
  PageHeader,
  SeleccionarUsuarioModal,
  StateMessage,
} from "../../components/ui";
import { labelRol } from "../../config/modulosPorRol";
import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";

import "./PermisosUsuario.css";

type ValorPermiso = null | boolean; // null = seguir default del rol

// Estado editable inicial = override actual (null → default del rol).
function edicionInicial(
  data: PermisoModuloDetalleDTO[],
): Record<string, ValorPermiso> {
  const inicial: Record<string, ValorPermiso> = {};
  for (const d of data) {
    inicial[`${d.clave}.crear`] = d.override.puede_crear;
    inicial[`${d.clave}.leer`] = d.override.puede_leer;
    inicial[`${d.clave}.actualizar`] = d.override.puede_actualizar;
    inicial[`${d.clave}.eliminar`] = d.override.puede_eliminar;
  }
  return inicial;
}

interface CeldaEditada {
  clave: string;
  campo: "crear" | "leer" | "actualizar" | "eliminar";
  valor: ValorPermiso;
}

export default function PermisosUsuario() {
  const [usuarios, setUsuarios] = useState<UsuarioPermisosDTO[] | null>(null);
  const [carnet, setCarnet] = useState<string>("");
  const [detalle, setDetalle] = useState<PermisoModuloDetalleDTO[] | null>(
    null,
  );
  const [edicion, setEdicion] = useState<Record<string, ValorPermiso>>({});
  const [guardando, setGuardando] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [selectorAbierto, setSelectorAbierto] = useState(false);
  // Carnet elegido mientras había cambios sin guardar: espera confirmación.
  const [cambioPendiente, setCambioPendiente] = useState<string | null>(null);

  // Navegar a otra sección con cambios sin guardar pide confirmación
  // (useBlocker del data router)...
  const bloqueo = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && currentLocation.pathname !== nextLocation.pathname,
  );

  // ...y cerrar o recargar la pestaña también (useBlocker no cubre eso).
  useEffect(() => {
    if (!dirty) return;
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [dirty]);

  const cargarUsuarios = useCallback(() => {
    let cancelado = false;
    listarUsuarios()
      .then((data) => {
        if (!cancelado) setUsuarios(data);
      })
      .catch((err) => {
        if (!cancelado)
          toast(
            mensajeError(err, "No se pudieron cargar los usuarios"),
            "error",
          );
      });
    return () => {
      cancelado = true;
    };
  }, []);

  useEffect(cargarUsuarios, [cargarUsuarios]);

  // Al elegir usuario, cargar sus permisos (override + efectivo).
  useEffect(() => {
    if (!carnet) {
      setDetalle(null);
      setEdicion({});
      setDirty(false);
      return;
    }
    let cancelado = false;
    setDetalle(null);
    listarPermisosUsuario(carnet)
      .then((data) => {
        if (cancelado) return;
        setDetalle(data);
        setEdicion(edicionInicial(data));
        setDirty(false);
      })
      .catch((err) => {
        if (!cancelado)
          toast(
            mensajeError(err, "No se pudieron cargar los permisos"),
            "error",
          );
      });
    return () => {
      cancelado = true;
    };
  }, [carnet]);

  const usuario = useMemo(
    () => usuarios?.find((u) => u.carnet === carnet) ?? null,
    [usuarios, carnet],
  );

  const esAdmin = usuario?.rol === "administrador";

  async function guardar() {
    if (!usuario) return;
    setGuardando(true);
    try {
      // null = seguir default del rol (sin override).
      const body: Record<string, PermisoOverrideDTO> = {};
      for (const d of detalle ?? []) {
        body[d.clave] = {
          puede_crear: edicion[`${d.clave}.crear`] ?? null,
          puede_leer: edicion[`${d.clave}.leer`] ?? null,
          puede_actualizar: edicion[`${d.clave}.actualizar`] ?? null,
          puede_eliminar: edicion[`${d.clave}.eliminar`] ?? null,
        };
      }
      await asignarPermisosUsuario(usuario.carnet, body);
      toast("Permisos guardados.", "success");
      // Recargar para mostrar efectivos actualizados.
      const data = await listarPermisosUsuario(usuario.carnet);
      setDetalle(data);
      setDirty(false);
    } catch (err) {
      toast(mensajeError(err, "No se pudieron guardar los permisos"), "error");
    } finally {
      setGuardando(false);
    }
  }

  const marcar = (
    clave: string,
    campo: CeldaEditada["campo"],
    valor: ValorPermiso,
  ) => {
    const key = `${clave}.${campo}`;
    setEdicion((prev) => ({ ...prev, [key]: valor }));
    setDirty(true);
  };

  return (
    <div className="permisos-usuario">
      <PageHeader
        title="Permisos por usuario"
        subtitle="Permisos CRUD por módulo, por usuario."
      />

      <div className="permisos-usuario__selector">
        <span id="permisos-usuario-label">Usuario:</span>
        <Button
          variant="secondary"
          aria-haspopup="dialog"
          aria-describedby="permisos-usuario-label"
          onClick={() => setSelectorAbierto(true)}
          disabled={usuarios === null}
        >
          {usuario
            ? `${usuario.carnet} · ${usuario.nombre}`
            : "Seleccionar usuario"}
        </Button>
      </div>
      <SeleccionarUsuarioModal
        open={selectorAbierto}
        usuarios={usuarios}
        seleccionado={usuario?.id}
        onSeleccionar={(u) => {
          setSelectorAbierto(false);
          if (dirty && u.carnet !== carnet) setCambioPendiente(u.carnet);
          else setCarnet(u.carnet);
        }}
        onClose={() => setSelectorAbierto(false)}
      />
      <ConfirmDialog
        open={bloqueo.state === "blocked"}
        title="Descartar cambios"
        message={`Hay cambios sin guardar en los permisos de ${usuario?.carnet ?? ""}. Si salís de esta página se pierden.`}
        confirmLabel="Descartar y salir"
        cancelLabel="Seguir editando"
        danger
        onConfirm={() => bloqueo.proceed?.()}
        onCancel={() => bloqueo.reset?.()}
      />
      <ConfirmDialog
        open={cambioPendiente !== null}
        title="Descartar cambios"
        message={`Hay cambios sin guardar en los permisos de ${usuario?.carnet ?? ""}. Si cambiás de usuario se pierden.`}
        confirmLabel="Descartar y cambiar"
        cancelLabel="Seguir editando"
        danger
        onConfirm={() => {
          setCarnet(cambioPendiente ?? "");
          setCambioPendiente(null);
        }}
        onCancel={() => setCambioPendiente(null)}
      />

      {usuario && (
        <p className="permisos-usuario__rol">
          Rol: <strong>{labelRol(usuario.rol)}</strong>
          {esAdmin &&
            " — los administradores no se pueden modificar (acceso total)."}
        </p>
      )}

      {detalle === null && carnet !== "" && (
        <StateMessage tipo="cargando">Cargando permisos...</StateMessage>
      )}

      {detalle !== null && (
        <>
          <DataTable<PermisoModuloDetalleDTO>
            columns={columnasPermisos(edicion, esAdmin, marcar)}
            rowKey={(d) => d.clave}
            rows={detalle}
            emptyMessage="Sin módulos."
          />
          {!esAdmin && (
            <div className="permisos-usuario__actions">
              {dirty && (
                <Button
                  variant="ghost"
                  disabled={guardando}
                  onClick={() => {
                    setEdicion(edicionInicial(detalle));
                    setDirty(false);
                  }}
                >
                  Descartar cambios
                </Button>
              )}
              <Button
                onClick={() => void guardar()}
                disabled={!dirty}
                loading={guardando}
              >
                Guardar permisos
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

type CampoCrud = "crear" | "leer" | "actualizar" | "eliminar";

const CAMPOS: { campo: CampoCrud; header: string }[] = [
  { campo: "crear", header: "Crear" },
  { campo: "leer", header: "Leer" },
  { campo: "actualizar", header: "Actualizar" },
  { campo: "eliminar", header: "Eliminar" },
];

function columnasPermisos(
  edicion: Record<string, ValorPermiso>,
  disabled: boolean,
  onMarcar: (clave: string, campo: CampoCrud, valor: ValorPermiso) => void,
): DataTableColumn<PermisoModuloDetalleDTO>[] {
  return [
    {
      key: "modulo",
      header: "Módulo",
      render: (d) => (
        <>
          <strong>{d.nombre}</strong>
          <span className="permisos-usuario__clave">{d.clave}</span>
        </>
      ),
    },
    ...CAMPOS.map(({ campo, header }) => ({
      key: campo,
      header,
      render: (d: PermisoModuloDetalleDTO) => (
        <SelectPermiso
          valor={edicion[`${d.clave}.${campo}`] ?? null}
          defaultRol={d.default_rol[`puede_${campo}`]}
          disabled={disabled}
          onChange={(v) => onMarcar(d.clave, campo, v)}
          label={`${campo} de ${d.nombre}`}
        />
      ),
    })),
  ];
}

function SelectPermiso({
  valor,
  defaultRol,
  disabled,
  onChange,
  label,
}: {
  valor: ValorPermiso;
  defaultRol: boolean;
  disabled: boolean;
  onChange: (v: ValorPermiso) => void;
  label: string;
}) {
  return (
    <select
      className={
        "select permisos-usuario__select" +
        (valor === null
          ? " permisos-usuario__select--default"
          : valor
            ? " permisos-usuario__select--on"
            : " permisos-usuario__select--off")
      }
      value={valor === null ? "" : String(valor)}
      onChange={(e) => {
        const v = e.target.value;
        onChange(v === "" ? null : v === "true");
      }}
      disabled={disabled}
      aria-label={label}
    >
      <option value="">Default ({defaultRol ? "sí" : "no"})</option>
      <option value="true">Permitir</option>
      <option value="false">Denegar</option>
    </select>
  );
}
