// LoginForm: form de login en 2 pasos (carnet+password -> codigo 2FA email).
//
// Fase 3E plan jurado: si el usuario tiene email_verificado, el backend
// responde {requiere_2fa: true} tras validar credenciales -> mostramos el
// input del codigo 6 digitos y lo verificamos antes de emitir tokens.
//
// Modo Operate: scanable, label visible, error via toast, accesible.

import { useNavigate } from "react-router-dom";
import { useState, type FormEvent } from "react";

import { useAuth } from "../context/useAuth";
import { toast } from "../lib/toasts";
import { NOMBRE_SISTEMA, SUBTITULO_LOGIN } from "../config/sistema";

import "./LoginForm.css";

type Paso = "credenciales" | "codigo";

export function LoginForm() {
  const { login, completar2fa } = useAuth();
  const navigate = useNavigate();
  const [paso, setPaso] = useState<Paso>("credenciales");
  const [carnet, setCarnet] = useState("");
  const [password, setPassword] = useState("");
  const [codigo, setCodigo] = useState("");
  const [loading, setLoading] = useState(false);

  function redirigir(rol: string) {
    if (rol === "administrador") {
      navigate("/admin", { replace: true });
    } else {
      navigate("/asistente", { replace: true });
    }
  }

  async function handleSubmitCredenciales(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const resp = await login(carnet, password);
      if (!("access_token" in resp)) {
        setPaso("codigo");
        toast("Código enviado a tu correo. Revisá tu email.", "info");
        return;
      }
      // Login legacy (sin 2FA configurado): tokens directos.
      toast(`Bienvenido, ${resp.nombre}`, "success");
      redirigir(resp.rol);
    } catch (err) {
      toast(mensajeError(err), "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitCodigo(e: FormEvent) {
    e.preventDefault();
    if (codigo.length !== 6) {
      toast("El código tiene 6 dígitos.", "warning");
      return;
    }
    setLoading(true);
    try {
      const resp = await completar2fa(carnet, codigo);
      toast(`Bienvenido, ${resp.nombre}`, "success");
      redirigir(resp.rol);
    } catch (err) {
      toast(mensajeError2Fa(err), "error");
    } finally {
      setLoading(false);
    }
  }

  function volverACredenciales() {
    setPaso("credenciales");
    setCodigo("");
  }

  return (
    <form
      onSubmit={
        paso === "credenciales" ? handleSubmitCredenciales : handleSubmitCodigo
      }
      className="login-form"
      noValidate
    >
      <div
        className="login-form__escudos"
        role="img"
        aria-label="Escudo de Bolivia y escudo de las Fuerzas Armadas"
      >
        <img
          className="login-form__escudo"
          src="/escudo-bolivia.png"
          alt="Escudo de Bolivia"
          width="48"
          height="48"
        />
        <img
          className="login-form__escudo"
          src="/escudo-fuerzas.png"
          alt="Escudo de las Fuerzas Armadas de Bolivia"
          width="44"
          height="44"
        />
      </div>
      <h1 className="login-form__title">{NOMBRE_SISTEMA}</h1>
      <p className="login-form__subtitle">{SUBTITULO_LOGIN}</p>

      {paso === "credenciales" ? (
        <>
          <label className="login-form__label" htmlFor="carnet">
            Carnet
          </label>
          <input
            id="carnet"
            type="text"
            autoComplete="username"
            value={carnet}
            onChange={(e) => setCarnet(e.target.value)}
            required
            minLength={4}
            maxLength={20}
            autoFocus
            className="login-form__input"
          />

          <label className="login-form__label" htmlFor="password">
            Contraseña
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            maxLength={128}
            className="login-form__input"
          />
        </>
      ) : (
        <>
          <p className="login-form__hint">
            Te enviamos un código de 6 dígitos al correo asociado al carnet{" "}
            <strong>{carnet}</strong>.
          </p>
          <label className="login-form__label" htmlFor="codigo">
            Código de verificación
          </label>
          <input
            id="codigo"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={codigo}
            onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ""))}
            required
            minLength={6}
            maxLength={6}
            autoFocus
            className="login-form__input login-form__input--codigo"
            placeholder="123456"
          />
        </>
      )}

      <button type="submit" disabled={loading} className="login-form__submit">
        {loading
          ? paso === "codigo"
            ? "Verificando..."
            : "Ingresando..."
          : paso === "codigo"
            ? "Verificar código"
            : "Ingresar"}
      </button>

      {paso === "codigo" && (
        <button
          type="button"
          className="login-form__back"
          onClick={volverACredenciales}
          disabled={loading}
        >
          ← Volver
        </button>
      )}
    </form>
  );
}

function mensajeError(err: unknown): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const resp = err as {
      response?: { status?: number; data?: { detail?: unknown } };
    };
    const status = resp.response?.status;
    if (status === 401) return "Credenciales inválidas.";
    if (status === 423) return "Cuenta bloqueada. Contactá al administrador.";
    if (status === 429)
      return "Demasiados intentos. Aguarda un minuto e intentá de nuevo.";
    if (status === 422 && Array.isArray(resp.response?.data?.detail)) {
      const msg = resp.response!.data!.detail[0]?.msg;
      if (typeof msg === "string") return msg;
    }
  }
  return "No se pudo conectar con el servidor.";
}

function mensajeError2Fa(err: unknown): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const resp = err as {
      response?: { status?: number; data?: { detail?: string } };
    };
    if (resp.response?.status === 401 && resp.response.data?.detail) {
      return resp.response.data.detail;
    }
    if (resp.response?.status === 423)
      return "Cuenta bloqueada por intentos 2FA fallidos. Contactá al administrador.";
    if (resp.response?.status === 429)
      return "Demasiados intentos. Aguarda 5 minutos.";
  }
  return "No se pudo verificar el código.";
}
