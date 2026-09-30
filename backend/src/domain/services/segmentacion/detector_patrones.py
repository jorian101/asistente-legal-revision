"""Servicio de dominio: DetectorPatrones — pre-segmentación por fuente.

Detecta qué segmentador (CPPM, CPE, CPM, LOJM, LOFA, CP, CPP)
coincide con un texto extraído de PDF, comparando una muestra del texto contra
los REGEX_ARTICULO y REGEX_ESTRUCTURA que ya tiene cada segmentador registrado.

No inventa patrones — lee los regex del código real en SegmentadorRegistry.
No hace I/O — recibe texto limpio (ya extraído por PyMuPDF) y devuelve scores.

Uso previsto: el admin sube un PDF → el sistema extrae muestra de texto →
detector sugiere abreviatura → interfaz muestra confianza antes de indexar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.services.segmentacion.registro import SegmentadorRegistry


@dataclass(slots=True)
class PatronDetectado:
    """Resultado de matchear un segmentador contra la muestra de texto."""

    abreviatura: str
    articulos_matcheados: int
    estructuras_detectadas: dict[str, int]
    confianza: float  # 0..1


@dataclass(slots=True)
class DeteccionResult:
    """Resultado completo de la detección de patrones por fuente."""

    candidatos: list[PatronDetectado] = field(default_factory=list)
    mejor: PatronDetectado | None = None
    error: str | None = None


class DetectorPatrones:
    """Detecta patrones de documento para pre-segmentación.

    Recorre SegmentadorRegistry (los segmentadores YA auto-registrados en
    python al importarlos) y aplica las REGEX_ARTICULO y REGEX_ESTRUCTURA de
    cada uno sobre la muestra de texto.
    """

    MUESTRA_CARACTERES = 20_000

    def detectar(self, texto_completo: str) -> DeteccionResult:
        """Detecta la fuente más probable para el texto extraído."""
        muestra = texto_completo[: self.MUESTRA_CARACTERES] if texto_completo else ""
        if not muestra.strip():
            return DeteccionResult(error="Texto vacío — no se pudo detectar patrones.")

        disponibles = SegmentadorRegistry.disponibles()
        if not disponibles:
            return DeteccionResult(error="No hay segmentadores registrados.")

        candidatos: list[PatronDetectado] = []
        for abreviatura in disponibles:
            seg = SegmentadorRegistry.obtener(abreviatura)
            n_arts = len(seg.REGEX_ARTICULO.findall(muestra))
            estructuras = {
                k: len(rgx.findall(muestra)) for k, (rgx, _nivel) in seg.REGEX_ESTRUCTURA.items()
            }
            confianza = self._calcular_confianza(seg.REGEX_ESTRUCTURA, n_arts, estructuras)
            candidatos.append(
                PatronDetectado(
                    abreviatura=abreviatura,
                    articulos_matcheados=n_arts,
                    estructuras_detectadas=estructuras,
                    confianza=confianza,
                )
            )

        candidatos.sort(key=lambda c: c.confianza, reverse=True)
        # Sin evidencia (cero artículos en todos): no se sugiere nada.
        # El fallback a candidatos[0] dependía del orden alfabético del
        # registry y sugería segmentadores sin fundamento (se rompió al
        # registrar SCP/CIDH, que ordenan antes que CP).
        mejor = next((c for c in candidatos if c.articulos_matcheados > 0), None)

        return DeteccionResult(candidatos=candidatos, mejor=mejor)

    def _calcular_confianza(
        self,
        regex_estructura: dict,
        n_arts: int,
        estructuras: dict[str, int],
    ) -> float:
        """Confianza empírica: peso fuerte en artículos, suplementa estructura.

        Devuelve: 0 si el artículo no aparece (su REGEX_ARTICULO no matchea → es definitivo).
        Si hay artículos: fracción de estructuras detectadas más peso base por
        tener artículos. Un segmentador con 0 artículos obtuvo confianza 0.
        """
        if n_arts == 0:
            return 0.0
        peso_articulo_base = 0.7
        peso_estructura_total = 0.3
        total_estructura_registrada = len(regex_estructura)
        if total_estructura_registrada == 0:
            return peso_articulo_base
        detectadas_vals = list(estructuras.values())
        estructuras_detectadas = sum(1 for v in detectadas_vals if v > 0)
        proporcion = estructuras_detectadas / total_estructura_registrada
        return peso_articulo_base + (peso_estructura_total * proporcion)
