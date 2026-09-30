import { useEffect, useState } from "react";

import {
  actualizarPerfil,
  obtenerPerfil,
  setAuthState,
  type PerfilDTO,
} from "../api/auth";
import { Button, PageHeader } from "../components/ui";
import { labelRol } from "../config/modulosPorRol";
import { useAuth } from "../context/useAuth";
import { mensajeError } from "../lib/errors";
import { toast } from "../lib/toasts";

import "./Perfil.css";

export default function Perfil() {
  const { auth } = useAuth();
  const [perfil, setPerfil] = useState<PerfilDTO | null>(null);
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [passwordActual, setPasswordActual] = useState("");
  const [passwordNueva, setPasswordNueva] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    obtenerPerfil()
      .then((data) => {
        setPerfil(data);
        setNombre(data.nombre);
        setEmail(data.email ?? "");
      })
      .catch((error) =>
        toast(mensajeError(error, "No se pudo cargar el perfil."), "error"),
      );
  }, []);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (passwordNueva && !passwordActual) {
      toast("Ingresá tu contraseña actual para cambiarla.", "warning");
      return;
    }
    setGuardando(true);
    try {
      const actualizado = await actualizarPerfil({
        nombre,
        email: email.trim() || null,
        password_actual: passwordActual || undefined,
        password_nueva: passwordNueva || undefined,
      });
      setPerfil(actualizado);
      setPasswordActual("");
      setPasswordNueva("");
      if (auth.access_token)
        setAuthState({ ...auth, nombre: actualizado.nombre });
      toast("Perfil actualizado.", "success");
    } catch (error) {
      toast(mensajeError(error, "No se pudo guardar el perfil."), "error");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="perfil-page">
      <PageHeader
        title="Mi perfil"
        subtitle="Actualizá tus datos de contacto y, si lo necesitás, tu contraseña."
      />
      <div className="perfil-page__grid">
        <section className="perfil-page__card perfil-page__card--identity">
          <span className="perfil-page__avatar" aria-hidden="true">
            {(perfil?.nombre ?? auth.nombre ?? "U").charAt(0).toUpperCase()}
          </span>
          <h2>{perfil?.nombre ?? auth.nombre ?? "Usuario"}</h2>
          <p>{perfil?.carnet ?? auth.carnet}</p>
          <dl>
            <div>
              <dt>Rol</dt>
              <dd>{labelRol(perfil?.rol ?? auth.rol)}</dd>
            </div>
            <div>
              <dt>Cargo</dt>
              <dd>{perfil?.cargo ?? "—"}</dd>
            </div>
          </dl>
          <small>
            El rol, cargo y carnet son administrados por el sistema.
          </small>
        </section>
        <form
          className="perfil-page__card perfil-page__form"
          onSubmit={guardar}
        >
          <h2>Datos editables</h2>
          <label>
            Nombre completo
            <input
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              minLength={2}
              required
            />
          </label>
          <label>
            Correo electrónico
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Sin correo"
            />
          </label>
          <div className="perfil-page__divider" />
          <h3>Cambiar contraseña</h3>
          <p className="perfil-page__hint">
            Dejá estos campos vacíos si no querés cambiarla.
          </p>
          <label>
            Contraseña actual
            <input
              className="input"
              type="password"
              value={passwordActual}
              onChange={(e) => setPasswordActual(e.target.value)}
              minLength={6}
            />
          </label>
          <label>
            Nueva contraseña
            <input
              className="input"
              type="password"
              value={passwordNueva}
              onChange={(e) => setPasswordNueva(e.target.value)}
              minLength={6}
            />
          </label>
          <Button
            type="submit"
            loading={guardando}
            disabled={perfil === null}
            className="perfil-page__guardar"
          >
            Guardar cambios
          </Button>
        </form>
      </div>
    </div>
  );
}
