// Página de login. Fondo institucional del tribunal, panel centrado sobrio.

import { LoginForm } from "../components/LoginForm";

import "./Login.css";

export default function Login() {
  return (
    <div className="login-page">
      <div className="login-page__background" aria-hidden="true">
        <img src="/fondo-supremo.jpg" alt="" />
      </div>
      <div className="login-page__panel">
        <LoginForm />
      </div>
      <footer className="login-page__footer">
        Sistema restringido — uso exclusivo del personal autorizado.
      </footer>
    </div>
  );
}
