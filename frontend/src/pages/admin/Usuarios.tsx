// Admin Usuarios: tabla + crear + modificar + reset password.
// HU-01 (crear) y HU-02 (modificar/reset). Visible solo para admin.
//
// Tabla via DataTable (mismo diseño que Auditoria/ConsultasHistorial):
// buscador (carnet/nombre/email) + filtros client-side (rol, cargo, estado,
// 2FA) + paginacion. Edicion por fila abre un Modal.

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, Eye, EyeOff, KeyRound } from "lucide-react";

import {
  type CrearUsuarioBody,
  type UsuarioDTO,
  api,
  crearUsuario,
  desbloquear2Fa,
  modificarUsuario,
  resetPassword,
} from "../../api/auth";

import { mensajeError } from "../../lib/errors";
import { toast } from "../../lib/toasts";
import {
  obtenerModulosVisibles,
  type ModuloVisibleDTO,
  type ModulosVisiblesDTO,
} from "../../api/permisos";
import { labelRol } from "../../config/modulosPorRol";
import { cargosParaRol } from "../../config/cargos";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../../components/DataTable";
import { PageHeader, Button, Modal, Badge, Field } from "../../components/ui";

import "./Usuarios.css";

const ROLES = ["administrador", "supervisor", "operador_juridico"] as const;
const POR_PAGINA = 10;

// Chip de un módulo efectivo: verde gestión, azul asistente.
function ChipModulo({ m }: { m: ModuloVisibleDTO }) {
  return (
    <span
      className={`usuarios-page__chip usuarios-page__chip--${
        m.ruta.startsWith("/admin") ? "green" : "blue"
      }`}
      title={m.descripcion}
    >
      {m.nombre}
    </span>
  );
}

// Módulos EFECTIVOS del usuario (rol ⊕ overrides, solo activos): los mismos
// que ve en su menú. null = cargando.
function ModulosCelda({ modulos }: { modulos: ModuloVisibleDTO[] | null }) {
  const [abierto, setAbierto] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    function handleClickOutside(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setAbierto(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [abierto]);

  return (
    <div className="usuarios-page__modulos-wrapper" ref={popoverRef}>
      <button
        type="button"
        className="usuarios-page__modulos-btn"
        onClick={() => setAbierto((prev) => !prev)}
        aria-expanded={abierto}
      >
        <span>{modulos === null ? "…" : `${modulos.length} módulos`}</span>
        <ChevronDown
          size={14}
          className={
            abierto ? "usuarios-page__modulos-chevron--open" : undefined
          }
          aria-hidden="true"
        />
      </button>
      {abierto && (
        <div className="usuarios-page__modulos-popover">
          <div className="usuarios-page__chips">
            {modulos?.map((m) => (
              <ChipModulo key={m.clave} m={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<UsuarioDTO[] | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [filtroRol, setFiltroRol] = useState("");
  const [filtroCargo, setFiltroCargo] = useState("");
  const [filtroActivo, setFiltroActivo] = useState("");
  const [filtro2Fa, setFiltro2Fa] = useState("");
  const [pagina, setPagina] = useState(1);
  const [editando, setEditando] = useState<UsuarioDTO | null>(null);
  const [modulosVis, setModulosVis] = useState<ModulosVisiblesDTO | null>(null);

  useEffect(() => {
    void cargar();
  }, []);

  async function cargar() {
    // Los módulos efectivos se recargan junto con la lista: un alta, un
    // cambio de rol o de estado los modifica.
    obtenerModulosVisibles()
      .then(setModulosVis)
      .catch(() => toast("No se pudieron cargar los módulos.", "error"));
    try {
      const { data } = await api.get<UsuarioDTO[]>("/admin/usuarios");
      setUsuarios(data);
    } catch {
      toast("No se pudo cargar la lista de usuarios.", "error");
    }
  }

  const todosCargos = useMemo(() => {
    const set = new Set<string>();
    ROLES.forEach((r) => cargosParaRol(r).forEach((c) => set.add(c)));
    return Array.from(set);
  }, []);

  const visibles = useMemo(() => {
    if (usuarios === null) return null;
    const q = busqueda.trim().toLowerCase();
    return usuarios.filter((u) => {
      if (filtroRol && u.rol !== filtroRol) return false;
      if (filtroCargo && u.cargo !== filtroCargo) return false;
      if (filtroActivo === "activo" && !u.activo) return false;
      if (filtroActivo === "inactivo" && u.activo) return false;
      if (filtro2Fa === "verificado" && !u.email_verificado) return false;
      if (filtro2Fa === "pendiente" && u.email_verificado) return false;
      if (q) {
        const hay = [u.carnet, u.nombre, u.email ?? ""].some((v) =>
          v.toLowerCase().includes(q),
        );
        if (!hay) return false;
      }
      return true;
    });
  }, [usuarios, busqueda, filtroRol, filtroCargo, filtroActivo, filtro2Fa]);

  function cambiarFiltro(setter: (v: string) => void, v: string) {
    setter(v);
    setPagina(1);
  }

  const paginados =
    visibles === null
      ? null
      : visibles.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);

  return (
    <div className="usuarios-page">
      <PageHeader
        title="Usuarios"
        subtitle="Gestión de usuarios y perfiles (HU-01, HU-02)."
      />
      <CrearForm
        onCreated={cargar}
        modulosPorRol={modulosVis?.por_rol ?? null}
      />
      <DataTable<UsuarioDTO>
        columns={columnas((u) => setEditando(u), cargar, modulosVis)}
        rowKey={(u) => u.id}
        rows={paginados}
        total={visibles?.length ?? null}
        page={pagina}
        pageSize={POR_PAGINA}
        onPageChange={setPagina}
        searchPlaceholder="Buscar por carnet, nombre o email..."
        searchValue={busqueda}
        onSearchChange={(v) => cambiarFiltro(setBusqueda, v)}
        emptyMessage="No hay usuarios que coincidan."
        filtros={
          <>
            <select
              value={filtroRol}
              onChange={(e) => cambiarFiltro(setFiltroRol, e.target.value)}
              aria-label="Filtrar por rol"
              className="select"
            >
              <option value="">Todos los roles</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {labelRol(r)}
                </option>
              ))}
            </select>
            <select
              value={filtroCargo}
              onChange={(e) => cambiarFiltro(setFiltroCargo, e.target.value)}
              aria-label="Filtrar por cargo"
              className="select"
            >
              <option value="">Todos los cargos</option>
              {todosCargos.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              value={filtroActivo}
              onChange={(e) => cambiarFiltro(setFiltroActivo, e.target.value)}
              aria-label="Filtrar por estado"
              className="select"
            >
              <option value="">Todos los estados</option>
              <option value="activo">Activos</option>
              <option value="inactivo">Inactivos</option>
            </select>
            <select
              value={filtro2Fa}
              onChange={(e) => cambiarFiltro(setFiltro2Fa, e.target.value)}
              aria-label="Filtrar por 2FA"
              className="select"
            >
              <option value="">2FA — todos</option>
              <option value="verificado">Verificado</option>
              <option value="pendiente">Pendiente</option>
            </select>
          </>
        }
      />

      {editando !== null && (
        <EditarUsuarioModal
          key={editando.id}
          usuario={editando}
          onClose={() => setEditando(null)}
          onChanged={() => {
            setEditando(null);
            cargar();
          }}
        />
      )}
    </div>
  );
}

function columnas(
  onEditar: (u: UsuarioDTO) => void,
  onChanged: () => void,
  modulosVis: ModulosVisiblesDTO | null,
): DataTableColumn<UsuarioDTO>[] {
  return [
    { key: "carnet", header: "Carnet" },
    { key: "nombre", header: "Nombre" },
    {
      key: "rol",
      header: "Rol",
      render: (u) => (
        <span className="usuarios-page__rol">{labelRol(u.rol)}</span>
      ),
    },
    { key: "cargo", header: "Cargo" },
    {
      key: "email",
      header: "Email",
      render: (u) => u.email ?? "—",
    },
    {
      key: "2fa",
      header: "2FA",
      render: (u) => (
        <Badge tone={u.email_verificado ? "success" : "warning"}>
          {u.email_verificado ? "Verificado" : "Pendiente"}
        </Badge>
      ),
    },
    {
      key: "modulos",
      header: "Módulos",
      render: (u) => (
        <ModulosCelda
          modulos={
            modulosVis === null
              ? null
              : (modulosVis.por_usuario[u.carnet] ?? [])
          }
        />
      ),
    },
    {
      key: "activo",
      header: "Activo",
      render: (u) => (
        <Badge tone={u.activo ? "success" : "warning"}>
          {u.activo ? "Activo" : "Inactivo"}
        </Badge>
      ),
    },
    {
      key: "acciones",
      header: "Acciones",
      render: (u) => (
        <AccionesUsuario
          usuario={u}
          onEditar={() => onEditar(u)}
          onChanged={onChanged}
        />
      ),
    },
  ];
}

function AccionesUsuario({
  usuario,
  onEditar,
  onChanged,
}: {
  usuario: UsuarioDTO;
  onEditar: () => void;
  onChanged: (() => void) | undefined;
}) {
  const navigate = useNavigate();
  const [confirmToggleActivo, setConfirmToggleActivo] = useState(false);
  const [guardandoToggle, setGuardandoToggle] = useState(false);
  const [resetAbierto, setResetAbierto] = useState(false);
  const [nuevaPassword, setNuevaPassword] = useState("");
  const [reseteando, setReseteando] = useState(false);
  const [confirmDesbloquear, setConfirmDesbloquear] = useState(false);
  const [desbloqueando, setDesbloqueando] = useState(false);
  const guardandoRef = useRef(false);

  async function toggleEstadoActivo() {
    if (guardandoRef.current) return;
    guardandoRef.current = true;
    const nuevoEstado = !usuario.activo;
    setGuardandoToggle(true);
    try {
      await modificarUsuario(usuario.carnet, {
        rol: usuario.rol as CrearUsuarioBody["rol"],
        cargo: usuario.cargo,
        activo: nuevoEstado,
        email: usuario.email ?? null,
      });
      toast(
        nuevoEstado ? "Usuario activado." : "Usuario desactivado.",
        "success",
      );
      setConfirmToggleActivo(false);
      onChanged?.();
    } catch (err) {
      toast(mensajeError(err, "No se pudo cambiar el estado."), "error");
    } finally {
      setGuardandoToggle(false);
      guardandoRef.current = false;
    }
  }

  async function desbloquear() {
    setDesbloqueando(true);
    try {
      await desbloquear2Fa(usuario.carnet);
      toast("2FA desbloqueado.", "success");
      setConfirmDesbloquear(false);
      onChanged?.();
    } catch (err) {
      toast(mensajeError(err, "No se pudo desbloquear."), "error");
    } finally {
      setDesbloqueando(false);
    }
  }

  // La contraseña tipeada no sobrevive al cierre del modal.
  function cerrarReset() {
    setResetAbierto(false);
    setNuevaPassword("");
  }

  async function confirmarReset(e: React.FormEvent) {
    e.preventDefault();
    setReseteando(true);
    try {
      await resetPassword(usuario.carnet, nuevaPassword);
      toast("Contraseña actualizada.", "success");
      cerrarReset();
    } catch (err) {
      toast(mensajeError(err, "No se pudo resetear la contraseña."), "error");
    } finally {
      setReseteando(false);
    }
  }

  return (
    <>
      <div className="usuarios-page__actions">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => navigate(`/admin/sala-control?usuario=${usuario.id}`)}
        >
          Ver consultas
        </Button>
        <Button size="sm" variant="secondary" onClick={onEditar}>
          Editar
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setConfirmToggleActivo(true)}
        >
          {usuario.activo ? "Desactivar" : "Activar"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setResetAbierto(true)}
        >
          Restablecer contraseña
        </Button>
        {usuario.email_verificado && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setConfirmDesbloquear(true)}
          >
            Desbloquear 2FA
          </Button>
        )}
      </div>

      <ConfirmDialog
        open={confirmToggleActivo}
        title={usuario.activo ? "Desactivar usuario" : "Activar usuario"}
        message={
          <>
            ¿Seguro que deseas {usuario.activo ? "desactivar" : "activar"} al
            usuario <strong>{usuario.carnet}</strong> ({usuario.nombre})?
          </>
        }
        confirmLabel={usuario.activo ? "Desactivar" : "Activar"}
        cancelLabel="Cancelar"
        danger={usuario.activo}
        busy={guardandoToggle}
        onConfirm={() => void toggleEstadoActivo()}
        onCancel={() => setConfirmToggleActivo(false)}
      />
      <ConfirmDialog
        open={confirmDesbloquear}
        title="Desbloquear 2FA"
        message={
          <>
            Se quitará el bloqueo de verificación en dos pasos de{" "}
            <strong>{usuario.carnet}</strong> ({usuario.nombre}) para que pueda
            volver a ingresar.
          </>
        }
        confirmLabel="Desbloquear"
        busy={desbloqueando}
        onConfirm={() => void desbloquear()}
        onCancel={() => setConfirmDesbloquear(false)}
      />
      <Modal
        open={resetAbierto}
        title={`Nueva contraseña para ${usuario.carnet}`}
        onClose={cerrarReset}
        busy={reseteando}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={cerrarReset} disabled={reseteando}>
              Cancelar
            </Button>
            <Button
              type="submit"
              form={`reset-${usuario.carnet}`}
              loading={reseteando}
              disabled={nuevaPassword.length < 6}
            >
              Actualizar contraseña
            </Button>
          </>
        }
      >
        <form
          id={`reset-${usuario.carnet}`}
          onSubmit={(e) => void confirmarReset(e)}
        >
          <Field
            id={`reset-pass-${usuario.carnet}`}
            label="Nueva contraseña"
            hint="Mínimo 6 caracteres."
          >
            <input
              id={`reset-pass-${usuario.carnet}`}
              autoFocus
              className="input"
              type="password"
              autoComplete="new-password"
              value={nuevaPassword}
              minLength={6}
              required
              onChange={(e) => setNuevaPassword(e.target.value)}
            />
          </Field>
        </form>
      </Modal>
    </>
  );
}

function CrearForm({
  onCreated,
  modulosPorRol,
}: {
  onCreated: () => void;
  /** Módulos que verá un usuario nuevo de cada rol (sin overrides). */
  modulosPorRol: Record<string, ModuloVisibleDTO[]> | null;
}) {
  const [carnet, setCarnet] = useState("");
  const [nombre, setNombre] = useState("");
  const [password, setPassword] = useState("");
  const [mostrarPassword, setMostrarPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<CrearUsuarioBody["rol"]>("operador_juridico");
  const [cargo, setCargo] = useState("");
  const [creando, setCreando] = useState(false);
  const cargos = cargosParaRol(rol);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCreando(true);
    try {
      await crearUsuario({
        carnet,
        nombre,
        password,
        rol,
        cargo,
        email: email.trim() || null,
      });
      toast("Usuario creado.", "success");
      setCarnet("");
      setNombre("");
      setPassword("");
      setEmail("");
      setCargo("");
      onCreated();
    } catch (err) {
      toast(mensajeError(err, "No se pudo crear el usuario."), "error");
    } finally {
      setCreando(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="usuarios-page__form">
      <h2>Crear usuario</h2>
      <div className="usuarios-page__row">
        <input
          className="input"
          placeholder="Carnet"
          aria-label="Carnet"
          value={carnet}
          onChange={(e) => setCarnet(e.target.value)}
          required
          minLength={4}
        />
        <input
          className="input"
          placeholder="Nombre"
          aria-label="Nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          required
        />
        <div className="usuarios-page__password-field">
          <input
            placeholder="Contraseña"
            aria-label="Contraseña"
            type={mostrarPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
          <button
            type="button"
            className="usuarios-page__password-action"
            title="Generar contraseña aleatoria"
            aria-label="Generar contraseña aleatoria"
            onClick={() => setPassword(generarPassword())}
          >
            <KeyRound size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="usuarios-page__password-action"
            title={
              mostrarPassword ? "Ocultar contraseña" : "Mostrar contraseña"
            }
            aria-label={
              mostrarPassword ? "Ocultar contraseña" : "Mostrar contraseña"
            }
            onClick={() => setMostrarPassword((visible) => !visible)}
          >
            {mostrarPassword ? (
              <EyeOff size={16} aria-hidden="true" />
            ) : (
              <Eye size={16} aria-hidden="true" />
            )}
          </button>
        </div>
        <input
          className="input"
          placeholder="Email (para 2FA)"
          aria-label="Email (para 2FA)"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <select
          className="select"
          aria-label="Rol"
          value={rol}
          onChange={(e) => {
            const nuevoRol = e.target.value as CrearUsuarioBody["rol"];
            setRol(nuevoRol);
            // Ajustar el cargo: si el actual no es válido para el nuevo rol,
            // resetear para forzar elección (Tabla 12).
            if (!cargosParaRol(nuevoRol).includes(cargo)) {
              setCargo("");
            }
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {labelRol(r)}
            </option>
          ))}
        </select>
        <select
          className="select"
          aria-label="Cargo"
          value={cargo}
          onChange={(e) => setCargo(e.target.value)}
        >
          <option value="" disabled>
            Cargo...
          </option>
          {cargos.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <Button
          type="submit"
          className="usuarios-page__submit-btn"
          loading={creando}
        >
          Crear
        </Button>
      </div>
      <div className="usuarios-page__chips usuarios-page__chips--preview">
        <span className="usuarios-page__chips-label">Accede a:</span>
        {modulosPorRol?.[rol]?.map((m) => (
          <ChipModulo key={m.clave} m={m} />
        ))}
      </div>
    </form>
  );
}

function EditarUsuarioModal({
  usuario,
  onClose,
  onChanged,
}: {
  usuario: UsuarioDTO;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [rol, setRol] = useState<CrearUsuarioBody["rol"]>(
    usuario.rol as CrearUsuarioBody["rol"],
  );
  const [cargo, setCargo] = useState(usuario.cargo);
  const [email, setEmail] = useState(usuario.email ?? "");
  const [activo, setActivo] = useState(usuario.activo);
  const [nombre, setNombre] = useState(usuario.nombre);
  const [carnet, setCarnet] = useState(usuario.carnet);
  const [guardando, setGuardando] = useState(false);
  const cargos = cargosParaRol(rol);

  function cambiarRol(nuevoRol: CrearUsuarioBody["rol"]) {
    setRol(nuevoRol);
    // Si el cargo actual no es válido para el nuevo rol, ajustar (Tabla 12).
    if (!cargosParaRol(nuevoRol).includes(cargo)) {
      const primero = cargosParaRol(nuevoRol)[0];
      setCargo(primero ?? "");
    }
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true);
    try {
      await modificarUsuario(usuario.carnet, {
        nombre: nombre.trim(),
        carnet: carnet.trim(),
        rol,
        cargo,
        activo,
        email: email.trim() || null,
      });
      toast("Guardado.", "success");
      onChanged();
    } catch (err) {
      toast(mensajeError(err, "No se pudo modificar."), "error");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Modal
      open
      title={`Editar usuario: ${usuario.carnet}`}
      onClose={onClose}
      busy={guardando}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={guardando}>
            Cancelar
          </Button>
          <Button type="submit" form="usuarios-edit-form" loading={guardando}>
            Guardar
          </Button>
        </>
      }
    >
      <form
        id="usuarios-edit-form"
        onSubmit={guardar}
        className="usuarios-page__edit-form"
      >
        <Field id="usuarios-edit-rol" label="Rol">
          <select
            id="usuarios-edit-rol"
            className="select"
            value={rol}
            onChange={(e) =>
              cambiarRol(e.target.value as CrearUsuarioBody["rol"])
            }
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {labelRol(r)}
              </option>
            ))}
          </select>
        </Field>
        <Field id="usuarios-edit-cargo" label="Cargo">
          <select
            id="usuarios-edit-cargo"
            className="select"
            value={cargo}
            onChange={(e) => setCargo(e.target.value)}
          >
            {cargos.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>
        <Field id="usuarios-edit-nombre" label="Nombre">
          <input
            id="usuarios-edit-nombre"
            className="input"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Nombre completo"
            required
            minLength={2}
          />
        </Field>
        <Field id="usuarios-edit-carnet" label="Carnet">
          <input
            id="usuarios-edit-carnet"
            className="input"
            value={carnet}
            onChange={(e) => setCarnet(e.target.value)}
            placeholder="CI o CM"
            required
            minLength={4}
          />
        </Field>
        <Field id="usuarios-edit-email" label="Email (para 2FA)">
          <input
            id="usuarios-edit-email"
            className="input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@dominio.com"
          />
        </Field>
        <label className="usuarios-page__check">
          <input
            type="checkbox"
            checked={activo}
            onChange={(e) => setActivo(e.target.checked)}
          />
          Activo
        </label>
      </form>
    </Modal>
  );
}

function generarPassword(): string {
  const caracteres =
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%";
  const valores = new Uint32Array(16);
  crypto.getRandomValues(valores);
  return Array.from(
    valores,
    (valor) => caracteres[valor % caracteres.length],
  ).join("");
}
