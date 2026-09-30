"""Servicio: ProcesadorContexto — procesamiento de contexto pre-LLM (F1).

Implementa el componente "Procesamiento de contexto" de la taxonomia de
ingenieria de contexto del marco-practico: refina la salida del pipeline
RAG antes de inyectarla al LLM.

Tres responsabilidades:
1. Deduplicacion: la expansion jerarquica (Sprint 5) puede ascender el
   mismo padre varias veces (alcanzado por hijos distintos). Un solo
   bloque por fragmento, conservando la primera aparicion.
2. Etiquetado de roles semanticos (SRL-lite, nivel 5 de Rothman):
   [NORMA] / [OBRADO] / etiquetas custom por obra (ej. DOCTRINA,
   CRITERIO) para que el LLM distinga la fuente de cada bloque.
3. Presupuesto: incluye bloques enteros hasta agotar el presupuesto de
   tokens aproximado. Nunca corta un bloque a mitad de texto (integridad
   juridica: un articulo truncado es peor que un articulo ausente).

Ponytail: presupuesto por aproximacion chars/token (default 4.0). Si la
precision importa, F2 lo reemplaza por tokenizer por endpoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.value_objects.contexto_expandido import ContextoExpandido


@dataclass(frozen=True)
class BloqueContexto:
    """Bloque atomico de contexto listo para inyectar al prompt."""

    etiqueta: str
    path: str
    texto: str

    def renderizar(self) -> str:
        """Formato: `[ETIQUETA · path]\\ntexto` (path opcional)."""
        encabezado = f"[{self.etiqueta} · {self.path}]" if self.path else f"[{self.etiqueta}]"
        return f"{encabezado}\n{self.texto}"


class ProcesadorContexto:
    """Refina ContextoExpandido en bloques deduplicados y presupuestados."""

    def __init__(self, max_tokens: int = 4096, chars_por_token: float = 4.0) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens debe ser >= 1")
        if chars_por_token <= 0:
            raise ValueError("chars_por_token debe ser > 0")
        self._max_chars = max(1, int(max_tokens * chars_por_token))

    def procesar(
        self,
        contexto: ContextoExpandido,
        *,
        etiquetas_obra: Mapping[int, str] | None = None,
    ) -> tuple[BloqueContexto, ...]:
        """Convierte el contexto expandido en bloques unicos dentro del presupuesto.

        Args:
            contexto: Salida del ExpansorContexto (Sprint 5).
            etiquetas_obra: Mapa opcional obra_id -> etiqueta (ej.
                {3: "DOCTRINA", 7: "CRITERIO"}). Sin entrada cae en OBRADO.

        Returns:
            Bloques unicos en orden de primera aparicion. Al menos 1 si hay
            fragmentos; vacio si el contexto no trae fragmentos.
        """
        return self._aplicar_presupuesto(self._a_bloques(contexto, etiquetas_obra or {}))

    def _a_bloques(
        self,
        contexto: ContextoExpandido,
        etiquetas_obra: Mapping[int, str],
    ) -> tuple[BloqueContexto, ...]:
        vistos: set[tuple[int | None, str]] = set()
        bloques: list[BloqueContexto] = []
        for idx, frag in enumerate(contexto.fragmentos_con_padres):
            clave = (frag.id, frag.qdrant_point_id)
            if clave in vistos:
                continue
            vistos.add(clave)

            breadcrumb = contexto.breadcrumbs[idx] if idx < len(contexto.breadcrumbs) else ()
            # Sin breadcrumb el path queda vacio: mostrar el qdrant_point_id
            # crudo filtraba UUIDs que el LLM citaba como referencia legal.
            path = " > ".join(breadcrumb) if breadcrumb else ""

            if frag.norma_id is not None:
                etiqueta = "NORMA"
            elif frag.obra_id is not None:
                etiqueta = etiquetas_obra.get(frag.obra_id, "OBRADO")
            else:
                etiqueta = "FRAGMENTO"

            bloques.append(BloqueContexto(etiqueta=etiqueta, path=path, texto=frag.texto))
        return tuple(bloques)

    def _aplicar_presupuesto(
        self, bloques: tuple[BloqueContexto, ...]
    ) -> tuple[BloqueContexto, ...]:
        """Incluye bloques enteros hasta agotar max_chars. Siempre >= 1 bloque."""
        seleccion: list[BloqueContexto] = []
        usados = 0
        for bloque in bloques:
            costo = len(bloque.renderizar()) + 2  # +2 por separador "\n\n---\n\n" aprox
            if seleccion and usados + costo > self._max_chars:
                break
            seleccion.append(bloque)
            usados += costo
        return tuple(seleccion)


__all__ = ["BloqueContexto", "ProcesadorContexto"]
