// SistemaLogo: isotipo institucional del sistema (escudo + balanza) para
// fondos oscuros. SVG puro, sin texto; el wordmark va por separado.
// Se usa en los sidebars generales (asistente y admin).

export function SistemaLogo({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="32"
      height="36"
      viewBox="0 0 30 34"
      focusable="false"
      aria-hidden="true"
    >
      <path
        d="M15 1 L28 5.5 V16 C28 24.5 22.5 30.5 15 33 C7.5 30.5 2 24.5 2 16 V5.5 Z"
        fill="rgba(255, 255, 255, 0.14)"
        stroke="#C9A227"
        strokeWidth="1.2"
      />
      <path
        d="M15 12 V20"
        stroke="#ffffff"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M7.5 11.5 H22.5"
        stroke="#ffffff"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M8.8 11.5 V15 M21.2 11.5 V15"
        stroke="#C9A227"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M6 15 Q8.8 18.5 11.6 15"
        stroke="#C9A227"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M18.4 15 Q21.2 18.5 24 15"
        stroke="#C9A227"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}
