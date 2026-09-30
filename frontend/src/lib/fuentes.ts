// Fuentes de los obrados: los formatos se extraen de Word/PDF y traen nombres internos
// ("ArialMT", "Arial-BoldMT", "TimesNewRomanPSMT") que ninguna computadora tiene instalados.
// Sin normalizar, el navegador caía en el respaldo `serif` y mostraba Times New Roman.

// Los obrados del Tribunal van en Arial: es la base y el respaldo de toda fuente.
export const FUENTE_BASE = 'Arial, "Helvetica Neue", Helvetica, sans-serif';

export function normalizarFuente(
  font: string | null | undefined,
): string | null {
  if (!font) return null;
  const familia = font
    .replace(/^[A-Z]{6}\+/, "") // prefijo de subconjunto de PDF: "ABCDEF+Arial"
    .replace(
      /[-,]?(BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular)?(PS)?MT$/,
      "",
    )
    .replace(/[-,](BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular)$/, "")
    .trim();
  if (!familia) return null;
  // "TimesNewRoman" -> "Times New Roman" (los nombres internos no llevan espacios)
  return familia.includes(" ")
    ? familia
    : familia.replace(/([a-z])([A-Z])/g, "$1 $2");
}

export function fuenteCss(font: string | null | undefined): string {
  const familia = normalizarFuente(font);
  return familia ? `"${familia}", ${FUENTE_BASE}` : FUENTE_BASE;
}
