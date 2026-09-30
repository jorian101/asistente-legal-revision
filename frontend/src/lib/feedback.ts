// Feedback localStorage — front-only mock para likes/dislikes (T3.1).
// Backend se hará después. Clave: "chat-feedback-{mensajeId}".

type Feedback = "like" | "dislike";

const STORAGE_PREFIX = "chat-feedback-";

export function getFeedback(mensajeId: string): Feedback | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}${mensajeId}`);
  return raw as Feedback | null;
}

export function setFeedback(mensajeId: string, feedback: Feedback): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(`${STORAGE_PREFIX}${mensajeId}`, feedback);
}

export function clearFeedback(mensajeId: string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(`${STORAGE_PREFIX}${mensajeId}`);
}

export function getAllFeedback(): Record<string, Feedback> {
  if (typeof window === "undefined") return {};
  const result: Record<string, Feedback> = {};
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(STORAGE_PREFIX)) {
      const id = key.slice(STORAGE_PREFIX.length);
      const val = localStorage.getItem(key);
      if (val === "like" || val === "dislike") {
        result[id] = val;
      }
    }
  }
  return result;
}
