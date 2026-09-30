import { NOMBRE_COMPLETO, SUBTITULO_LOGIN } from "../config/sistema";

import "./Footer.css";

export function Footer() {
  return (
    <footer className="app-footer">
      <span>{NOMBRE_COMPLETO}</span>
      <span aria-hidden="true">·</span>
      <span>{SUBTITULO_LOGIN}</span>
      <span aria-hidden="true">·</span>
      <span>© {new Date().getFullYear()}</span>
    </footer>
  );
}
