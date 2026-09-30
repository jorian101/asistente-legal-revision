// Composición de la etiqueta visible de una fuente RAG (cita bajo el mensaje
// del asistente). Función PURA, sin React: se prueba como unit test plano, sin
// render ni navegador. El backend devuelve campos crudos; acá se arma el texto
// legible que lee el usuario ("Auto de Vista · Exp. 3349", "LOJM 3", ...).

import type { FragmentoCita } from "./chatTypes";

export type CategoriaFuente =
  "norma" | "jurisprudencia" | "doctrina" | "obrado" | "fragmento";

export interface EtiquetaFuente {
  /** Badge de categoría: NORMA | JURISPRUDENCIA | DOCTRINA | OBRADO | FRAGMENTO. */
  badge: string;
  /** Categoría de la fuente (para estilo y para el resumen). */
  categoria: CategoriaFuente;
  /** True si es norma o jurisprudencia. */
  esNorma: boolean;
  /** Etiqueta legible "qué es / dónde buscarla". Null si no hay nada. */
  etiqueta: string | null;
}

/** Convierte un token interno tipo "auto_vista" a etiqueta legible "Auto Vista". */
function tituloCapital(token: string): string {
  return token.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Tipos de obra que no son un obrado del caso (espejo de categoria_fuente.py).
const TIPOS_DOCTRINA = new Set([
  "doctrina",
  "criterio",
  "doctrina_libro",
  "material_caso",
]);
const TIPOS_JURISPRUDENCIA = new Set(["jurisprudencia", "ejemplo"]);
const CATEGORIAS = new Set(["norma", "jurisprudencia", "doctrina", "obrado"]);

/**
 * Categoría de la fuente. La decide el backend (`categoria`); si no llega
 * (mensajes antiguos), se deduce como en categoria_fuente.py.
 */
function categoriaDe(fragmento: FragmentoCita): CategoriaFuente {
  if (fragmento.categoria && CATEGORIAS.has(fragmento.categoria)) {
    return fragmento.categoria as CategoriaFuente;
  }
  if (fragmento.norma_id !== null) return "norma";
  if (fragmento.obra_id === null) return "fragmento";
  if (fragmento.obra_tipo && TIPOS_JURISPRUDENCIA.has(fragmento.obra_tipo)) {
    return "jurisprudencia";
  }
  if (fragmento.obra_tipo && TIPOS_DOCTRINA.has(fragmento.obra_tipo)) {
    return "doctrina";
  }
  return "obrado";
}

const BADGE: Record<CategoriaFuente, string> = {
  norma: "NORMA",
  jurisprudencia: "JURISPRUDENCIA",
  doctrina: "DOCTRINA",
  obrado: "OBRADO",
  fragmento: "FRAGMENTO",
};

/** Resumen de fuentes por categoría: "3 normas · 2 obrados · 1 doctrina". */
export function resumenFuentes(fragmentos: FragmentoCita[]): string {
  const cuenta: Record<CategoriaFuente, number> = {
    norma: 0,
    jurisprudencia: 0,
    doctrina: 0,
    obrado: 0,
    fragmento: 0,
  };
  for (const f of fragmentos) cuenta[categoriaDe(f)] += 1;

  const partes: string[] = [];
  if (cuenta.norma > 0)
    partes.push(`${cuenta.norma} ${cuenta.norma === 1 ? "norma" : "normas"}`);
  if (cuenta.jurisprudencia > 0)
    partes.push(`${cuenta.jurisprudencia} jurisprudencia`);
  if (cuenta.obrado > 0)
    partes.push(
      `${cuenta.obrado} ${cuenta.obrado === 1 ? "obrado" : "obrados"}`,
    );
  if (cuenta.doctrina > 0) partes.push(`${cuenta.doctrina} doctrina`);
  if (cuenta.fragmento > 0)
    partes.push(
      `${cuenta.fragmento} ${cuenta.fragmento === 1 ? "fuente" : "fuentes"}`,
    );
  return partes.join(" · ");
}

export function etiquetaFuente(fragmento: FragmentoCita): EtiquetaFuente {
  const categoria = categoriaDe(fragmento);
  const esNorma = categoria === "norma" || categoria === "jurisprudencia";
  const badge = BADGE[categoria];

  let etiqueta: string | null;
  if (fragmento.norma_id !== null) {
    const nombre = fragmento.norma_nombre ?? null;
    const abrev = fragmento.norma_abreviatura ?? null;
    // Solo agrega el nombre formal si APORTA algo distinto de la abreviatura
    // (en datos reales `nombre` suele ser igual a `abreviatura` y duplicaría
    // "LOJM · LOJM 3"). Si no suma, queda la referencia legible (slug).
    const sumaInfo =
      nombre !== null &&
      nombre.trim().toUpperCase() !== (abrev ?? "").trim().toUpperCase();
    etiqueta = sumaInfo
      ? `${nombre}${fragmento.referencia ? ` · ${fragmento.referencia}` : ""}`
      : (fragmento.referencia ?? nombre ?? abrev);
  } else if (categoria === "doctrina") {
    // La doctrina no pertenece a un expediente: sin "Exp.".
    etiqueta = [
      tituloCapital(fragmento.obra_tipo ?? "doctrina"),
      fragmento.obra_fecha_documento || null,
    ]
      .filter(Boolean)
      .join(" · ");
  } else if (esNorma) {
    etiqueta = fragmento.referencia ?? tituloCapital(fragmento.obra_tipo ?? "");
  } else if (fragmento.obra_tipo) {
    etiqueta = [
      tituloCapital(fragmento.obra_tipo),
      fragmento.expediente_numero
        ? `Exp. ${fragmento.expediente_numero}`
        : null,
      fragmento.obra_fecha_documento || null,
    ]
      .filter(Boolean)
      .join(" · ");
  } else {
    etiqueta = fragmento.referencia;
  }

  return { badge, categoria, esNorma, etiqueta };
}
