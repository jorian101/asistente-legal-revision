// Util compartido: extrae el mensaje de error del backend (detail) o usa fallback.

export function mensajeError(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })
      .response?.data?.detail;
    if (typeof detail === "string") return detail;
    // RequisitosIncompletosError devuelve {message, faltantes, tipo_proceso}
    if (
      detail !== null &&
      typeof detail === "object" &&
      "message" in (detail as Record<string, unknown>) &&
      typeof (detail as Record<string, unknown>).message === "string"
    ) {
      return String((detail as Record<string, unknown>).message);
    }
    // FastAPI/pydantic valida con 422 y detail es un array de errores.
    // Mostrar el primer mensaje legible (msg) en vez del fallback generico.
    if (Array.isArray(detail)) {
      const msg = detail[0]?.msg;
      if (typeof msg === "string") return msg;
    }
  }
  // responderConsulta ya pone el detail.message en err.message
  if (err instanceof Error && err.message && err.message !== fallback) {
    // Si el message parece venir del backend (contiene el texto del detail),
    // usarlo. Evita mostrar el boilerplate "POST /consultas/responder status 422: ..."
    // cuando el detail ya tiene un mensaje legible.
    if (
      err.message.includes("No se pudo generar") ||
      err.message.includes("Faltan obrados")
    ) {
      return err.message;
    }
  }
  return fallback;
}
