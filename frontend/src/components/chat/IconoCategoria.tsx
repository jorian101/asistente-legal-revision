// Icono de una categoría de fuente (mismos que los botones del chat):
// normas = Landmark, jurisprudencia = Scale, doctrina = BookMarked.

import { BookMarked, Landmark, Scale } from "lucide-react";

import type { CategoriaFuente } from "../../api/fuentes";

const ICONOS = {
  norma: Landmark,
  jurisprudencia: Scale,
  doctrina: BookMarked,
} as const;

export function IconoCategoria({
  categoria,
  size = 14,
}: {
  categoria: CategoriaFuente;
  size?: number;
}) {
  const Icono = ICONOS[categoria];
  return <Icono size={size} aria-hidden="true" data-categoria={categoria} />;
}
