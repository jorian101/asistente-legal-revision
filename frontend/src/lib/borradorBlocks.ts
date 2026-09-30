// Adapter: contenido .md <-> bloques fieles (dual md + layout).
//
// Un borrador tiene dos representaciones que se actualizan juntas al
// "Guardar todo":
//   - contenido (.md): texto con ## para encabezados (card, chat, historial)
//   - layout (fiel): bloques con align/bold/size/font/heading para preview+export
//
// Si el borrador trae layout, es la fuente de verdad del estilo.
// Si no (borrador viejo / primer render), se deriva del .md con #/##.

import type { BloqueDTO } from "../api/formatos";

export interface BloqueBorradorDTO {
  texto: string;
  align: string;
  bold: boolean;
  underline: boolean;
  size_pt: number | null;
  font: string | null;
  heading: number; // 0 body, 1 "# ", 2 "## "
}

function esAllCapsHeading(texto: string): boolean {
  const s = texto.trim();
  return (
    s.length > 0 &&
    s.length <= 80 &&
    s === s.toUpperCase() &&
    /[A-ZÁÉÍÓÚÑ]/.test(s)
  );
}

function inferBloqueDeLinea(linea: string): BloqueBorradorDTO {
  const raw = linea.trim();
  if (raw.startsWith("# ")) {
    return {
      texto: raw.slice(2).trim(),
      align: "center",
      bold: true,
      underline: false,
      size_pt: null,
      font: null,
      heading: 1,
    };
  }
  if (raw.startsWith("## ")) {
    return {
      texto: raw.slice(3).trim(),
      align: "center",
      bold: true,
      underline: false,
      size_pt: null,
      font: null,
      heading: 2,
    };
  }
  if (esAllCapsHeading(raw)) {
    return {
      texto: raw,
      align: "center",
      bold: true,
      underline: false,
      size_pt: null,
      font: null,
      heading: 1,
    };
  }
  return {
    texto: raw,
    align: "justify",
    bold: false,
    underline: false,
    size_pt: null,
    font: null,
    heading: 0,
  };
}

export function contenidoToBloques(contenido: string): BloqueBorradorDTO[] {
  const out: BloqueBorradorDTO[] = [];
  for (const linea of contenido.split("\n")) {
    const t = linea.trim();
    if (!t) continue;
    out.push(inferBloqueDeLinea(t));
  }
  return out;
}

export function layoutToBloques(
  layout: BloqueBorradorDTO[] | null,
): BloqueBorradorDTO[] | null {
  if (!layout || layout.length === 0) return null;
  // Normalizar con defaults defensivos
  return layout.map((b) => ({
    texto: b.texto ?? "",
    align: b.align ?? "justify",
    bold: !!b.bold,
    underline: !!b.underline,
    size_pt: b.size_pt ?? null,
    font: b.font ?? null,
    heading: b.heading ?? 0,
  }));
}

export function bloquesToContenido(bloques: BloqueBorradorDTO[]): string {
  return bloques
    .map((b) => {
      const t = b.texto.trim();
      if (!t) return "";
      if (b.heading === 1) return `# ${t}`;
      if (b.heading === 2) return `## ${t}`;
      return t;
    })
    .filter(Boolean)
    .join("\n");
}

export function bloquesToLayout(
  bloques: BloqueBorradorDTO[],
): BloqueBorradorDTO[] {
  return bloques.map((b) => ({ ...b }));
}

// Convierte BloqueBorradorDTO[] al shape BloqueDTO[] que espera DocumentoPreview.
// Cada bloque se mapea a page=1, index=i con un solo run.
export function bloquesToPreviewBloques(
  bloques: BloqueBorradorDTO[],
): BloqueDTO[] {
  return bloques.map((b, i) => ({
    page: 1,
    index: i,
    kind: "paragraph",
    align: b.align,
    bbox: null,
    confidence: 1,
    runs: [
      {
        text: b.texto,
        bold: b.bold,
        underline: b.underline,
        allcaps: false,
        size_pt: b.size_pt,
        font: b.font,
      },
    ],
  }));
}

// Resuelve los bloques efectivos de un borrador: layout si existe, sino .md.
export function bloquesEfectivos(
  contenido: string,
  layout: BloqueBorradorDTO[] | null | undefined,
): BloqueBorradorDTO[] {
  const l = layoutToBloques(layout as BloqueBorradorDTO[] | null);
  if (l) return l;
  return contenidoToBloques(contenido);
}

// Texto sin marcas de Markdown para resúmenes (tarjeta de obrado): **negrita**,
// __negrita__, `código` y los "#"/">" de inicio de línea no deben verse literales.
export function textoPlano(contenido: string): string {
  return contenido.replace(/\*\*|__|`/g, "").replace(/^\s*(#{1,6}|>)\s*/gm, "");
}
