"""Caso de uso: seleccionar un ítem de corpus N2/N3 para un expediente.

Crea una obra PUNTERO (sin duplicar contenido): tipo_documento según
jerarquía (jurisprudencia/doctrina_libro), corpus+corpus_ref con la
abreviatura de la norma, privada por defecto (Regla 5). El pipeline
resuelve punteros a recuperación explícita por abreviatura.

No toca criterios ni el flujo de copia de obras globales.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.obra import Obra
from src.domain.services.categoria_fuente import categoria_de_jerarquia

_TIPO_POR_JERARQUIA = {
    "jurisprudencia": "jurisprudencia",
    "doctrina": "doctrina_libro",
    "suprema": "norma_corpus",
    "militar": "norma_corpus",
    "supletoria": "norma_corpus",
}


@dataclass(frozen=True, slots=True)
class SeleccionarCorpusRequest:
    """Entrada: abreviatura de norma N2/N3 + destino."""

    abreviatura: str  # ej: 'SCP-0623-2024-S4', 'LIB-ATIENZA-INTERP-2019'
    propietario_id: int
    expediente_id: int | None = None


@dataclass(frozen=True, slots=True)
class SeleccionarCorpusResponse:
    """Salida: id de la obra puntero creada."""

    obra_id: int
    estado_visibilidad: str


class CorpusNoSeleccionableError(LookupError):
    """La abreviatura no existe o no es N2/N3 (leyes no se seleccionan)."""


class SeleccionarCorpus:
    """Crea el puntero de un ítem N2/N3 para el caso o consulta."""

    def __init__(self, obra_repo, norma_repo) -> None:
        self._obra_repo = obra_repo
        self._norma_repo = norma_repo

    async def ejecutar(self, request: SeleccionarCorpusRequest) -> SeleccionarCorpusResponse:
        """Crea la obra puntero.

        Raises:
            CorpusNoSeleccionableError: si la norma no existe, no está
                indexada o no es jurisprudencia/doctrina.
        """
        norma = await self._norma_repo.get_by_abreviatura(request.abreviatura)
        if norma is None or not norma.indexado or norma.jerarquia not in _TIPO_POR_JERARQUIA:
            raise CorpusNoSeleccionableError(
                f"'{request.abreviatura}' no es una fuente indexada "
                "(norma, jurisprudencia o doctrina)."
            )
        # Solo lo global o lo propio: una fuente privada o pendiente de otro no se fija.
        es_propia = norma.propietario_id == request.propietario_id
        if norma.estado_visibilidad != "global" and not (
            es_propia and norma.estado_visibilidad in ("privado", "pendiente")
        ):
            raise CorpusNoSeleccionableError(f"'{request.abreviatura}' no está disponible.")

        puntero = Obra(
            id=None,
            expediente_id=request.expediente_id,
            propietario_id=request.propietario_id,
            tipo_documento=_TIPO_POR_JERARQUIA[norma.jerarquia],  # type: ignore[arg-type]
            nombre_archivo=norma.nombre,
            contenido_texto="",
            ruta_archivo=None,
            fojas_inicio=None,
            fojas_fin=None,
            estado_visibilidad="privado",
            fuente="carga_usuario",
            tamano_archivo=0,
            estado_procesamiento="completado",
            corpus=categoria_de_jerarquia(norma.jerarquia),
            corpus_ref=norma.abreviatura,
        )
        guardada = await self._obra_repo.guardar(puntero)
        return SeleccionarCorpusResponse(
            obra_id=guardada.id,  # type: ignore[arg-type]
            estado_visibilidad=guardada.estado_visibilidad,
        )
