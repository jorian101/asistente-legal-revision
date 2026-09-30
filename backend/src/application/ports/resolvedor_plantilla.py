"""Port: ResolvedorPlantilla — stub para Sprint 6 (Plantillas de prompt).

Sprint 6 implementa el adapter que lee plantillas desde docs/plantillas/*.md
y aplica variables del expediente.

Plantillas disponibles (marco-practico.md):
- consulta_simple → Anexo V
- auto_vista_consulta → Anexo X (auto de vista consulta de oficio)
- auto_vista_apelacion_incidental → Anexo X (apelacion incidental)

Fase 3 (G1): el port acepta un kwarg opcional `vicios` de tipo
ResultadoVicios (ver domain.value_objects.resultado_vicios) para que el
adapter resuelva {{CONDICIONAL_LOGICA_SANEAMIENTO:
SI_EXISTE_VICIO_DE_NULIDAD}} con vicios reales detectados por
AnalizadorVicios (domain.services.analizador_vicios), en vez del
placeholder hardcodeado "[No se detectó vicio...]".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.domain.value_objects.contexto_recuperado import TipoRespuesta

if TYPE_CHECKING:
    from src.domain.value_objects.resultado_vicios import ResultadoVicios


class ResolvedorPlantilla(Protocol):
    """Port hacia Sprint 6 (Plantillas de prompt — Anexos V/W/X).

    Sprint 6 implementa el adapter que lee plantillas y aplica variables
    del expediente para producir el prompt completo.
    """

    def resolver(
        self,
        tipo_respuesta: TipoRespuesta,
        expediente_id: int | None,
        *,
        vicios: ResultadoVicios | None = None,
        usuario_id: int | None = None,
    ) -> str:
        """Resuelve la plantilla segun el tipo de respuesta.

        Args:
            tipo_respuesta: Tipo de respuesta (determina que plantilla usar).
            expediente_id: ID del expediente (para resolver variables). None
                si es consulta_simple.
            vicios: Resultado de AnalizadorVicios sobre los fragmentos del
                contexto (Fase 3 G1). None si el caller no corre analisis
                de vicios — el adapter usara el fallback conservador
                "[No se detecto vicio de nulidad en este analisis
                automatico.]".
            usuario_id: ID del usuario que genera el borrador. Se usa para
                resolver fojas desde las obras del expediente (Regla 5:
                solo obras propias o publicadas). None si no aplica
                (consulta_simple).

        Returns:
            String del prompt completo con variables resueltas. El prompt
            incluye slots {{contexto_expandido}} y {{consulta_usuario}}
            que el caller (use case Sprint 6) llena con los valores reales.

        Raises:
            ValueError: Si tipo_respuesta requiere expediente y no se provee.
        """
        ...
