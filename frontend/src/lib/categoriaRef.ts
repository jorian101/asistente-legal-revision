// Categoría de una fuente fijada en el chat, deducida del prefijo de su abreviatura
// (convención del corpus): LIB- libros (doctrina); SC-, SCP-, CIDH- y JUR- sentencias
// (jurisprudencia); el resto son normas (CPE, CPP, LEY-…).

import type { CategoriaFuente } from "../api/fuentes";

export function categoriaDeRef(ref: string): CategoriaFuente {
  if (ref.startsWith("LIB-")) return "doctrina";
  if (/^(SCP?|CIDH|JUR)-/.test(ref)) return "jurisprudencia";
  return "norma";
}
