"""Registry de segmentadores por corpus.

Mapea abreviatura de norma -> clase SegmentadorNorma.
Permite resolver el segmentador correcto en tiempo de ejecución
sin acoplar código de infraestructura a implementaciones concretas.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.domain.services.segmentacion.base import SegmentadorNorma

if TYPE_CHECKING:
    from src.domain.entities.norma import Norma


class SegmentadorRegistry:
    """Registry singleton para segmentadores por corpus.

    Uso:
        registry = SegmentadorRegistry()
        segmentador = registry.obtener('CPPM')
        arbol = segmentador.segmentar(texto_extraido)
    """

    _instancia: SegmentadorRegistry | None = None
    _mapa: dict[str, type[SegmentadorNorma]] = {}
    #: Fabricas genericas por categoria (norma | jurisprudencia | doctrina): sirven a
    #: las fuentes que suben los usuarios y no tienen segmentador propio.
    _categorias: dict[str, Callable[[str], SegmentadorNorma]] = {}

    def __new__(cls) -> SegmentadorRegistry:
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._mapa = {}
        return cls._instancia

    @classmethod
    def registrar(cls, abreviatura: str, segmentador_cls: type[SegmentadorNorma]) -> None:
        """Registra un segmentador para una abreviatura.

        Args:
            abreviatura: Clave canónica (ej: 'CPPM', 'CPM', 'CPE').
            segmentador_cls: Clase concreta que hereda de SegmentadorNorma.

        Raises:
            ValueError: Si la abreviatura ya está registrada con otra clase.
        """
        if abreviatura in cls._mapa:
            existente = cls._mapa[abreviatura]
            if existente is not segmentador_cls:
                raise ValueError(
                    f"Segmentador para '{abreviatura}' ya registrado: {existente.__name__}. "
                    f"Intento de sobrescribir con {segmentador_cls.__name__}."
                )
        else:
            cls._mapa[abreviatura] = segmentador_cls

    @classmethod
    def registrar_categoria(
        cls, categoria: str, fabrica: Callable[[str], SegmentadorNorma]
    ) -> None:
        """Registra la fabrica de segmentadores genericos de una categoria de fuente."""
        cls._categorias[categoria] = fabrica

    @classmethod
    def obtener(cls, abreviatura: str, categoria: str | None = None) -> SegmentadorNorma:
        """Obtiene una instancia del segmentador para la abreviatura.

        Args:
            abreviatura: Clave canónica (ej: 'CPPM').

        Returns:
            Instancia del segmentador registrado.

        Raises:
            KeyError: Si no hay segmentador registrado para la abreviatura.
        """
        if abreviatura not in cls._mapa and categoria in cls._categorias:
            return cls._categorias[categoria](abreviatura)
        try:
            return cls._mapa[abreviatura]()
        except KeyError as exc:
            disponibles = ", ".join(sorted(cls._mapa.keys()))
            raise KeyError(
                f"No hay segmentador registrado para '{abreviatura}'. Disponibles: {disponibles}"
            ) from exc

    @classmethod
    def obtener_para_norma(cls, norma: Norma) -> SegmentadorNorma:
        """Obtiene segmentador usando la abreviatura de una entidad Norma."""
        return cls.obtener(norma.abreviatura)

    @classmethod
    def disponibles(cls) -> list[str]:
        """Lista abreviaturas con segmentadores registrados."""
        return sorted(cls._mapa.keys())

    @classmethod
    def limpiar(cls) -> None:
        """Limpia el registry (útil para tests)."""
        cls._mapa.clear()
        cls._instancia = None


# ----- Auto-registro de segmentadores ----------------------------------------
# Se importan aquí para que el registro ocurra al importar este módulo.
# Cada segmentador concreto debe importarse e invocar registrar().

# Nota: Los segmentadores concretos (cppm.py, cpm.py, etc.) se registran
# al ser importados. Para que funcione, deben importar este módulo y llamar:
#   from src.domain.services.segmentacion.registro import SegmentadorRegistry
#   SegmentadorRegistry.registrar('CPPM', SegmentadorCPPM)

# Este patrón evita imports circulares: el registry no conoce a los
# segmentadores concretos, son ellos los que se auto-registran.
