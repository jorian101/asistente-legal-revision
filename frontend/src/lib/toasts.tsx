// Toasts globales — portal root, 3 clases CSS, setTimeout. Sin librería externa.

import { useEffect, useState } from "react";
import * as ReactDOM from "react-dom";

import "./ToastContainer.css";

type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

let toasts: Toast[] = [];
let listeners: Array<() => void> = [];

function notify() {
  listeners.forEach((l) => l());
}

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function toast(
  message: string,
  type: ToastType = "info",
  duration = 4000,
) {
  const t: Toast = { id: genId(), message, type, duration };
  toasts = [...toasts, t];
  notify();
  if (duration > 0) {
    setTimeout(() => dismiss(t.id), duration);
  }
  return t.id;
}

export function dismiss(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  notify();
}

export function useToasts() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const listener = () => setTick((n) => n + 1);
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  }, []);
  return { toasts, dismiss };
}

export function ToastContainer() {
  const { toasts, dismiss } = useToasts();

  if (toasts.length === 0) return null;

  return ReactDOM.createPortal(
    <div
      className="toast-container"
      role="region"
      aria-label="Notificaciones"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast--${t.type}`}
          role="alert"
          aria-live="assertive"
        >
          <span className="toast__message">{t.message}</span>
          <button
            className="toast__close"
            onClick={() => dismiss(t.id)}
            aria-label="Cerrar"
          >
            ✕
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}
