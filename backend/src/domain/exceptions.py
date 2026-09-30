"""Excepciones de dominio.

Excepciones puras del dominio (no dependen de infra ni de UI). Las routers
las envuelven en HTTPException; los use cases las levantan para se
propaguen al caller.
"""


class DomainError(Exception):
    """Base para errores del dominio."""


class ConsultaSinExpedienteError(DomainError):
    """La consulta requiere expediente_id pero no fue provisto.

    Disparado por ClasificadorTipoRespuesta cuando la consulta se clasifica
    como auto_vista_* y no se provee expediente_id (las plantillas V/X
    dependen del expediente activo).
    """


class BorradorNoPropioError(DomainError, PermissionError):
    """Intento de publicar/ver un borrador de otro usuario (Regla 7).

    Trail of Bits Regla 7 BLOQUEANTE: solo el propietario puede cambiar
    estado a 'publicado'. El adapterPostgresBorradorRepo.actualizar_estado
    filtra por propietario_id; si no matchea devuelve None y el use case
    PublicarBorrador levanta esta excepcion (403 en router).
    """


class PlantillaNoImplementadaError(DomainError):
    """Tipo de respuesta requiere plantilla que no existe aun en disco.

    Caso: dictamen_radicatoria no tiene plantilla en docs/plantillas/ —
    el usuario la provee posteriormente. El adapter levanta esta excepcion
    y el router mapea a 422 con mensaje claro (no 500).
    """


class BorradorVacioError(DomainError):
    """Intento de publicar un borrador sin contenido generado (Regla 7).

    no-mistakes codex round 3: el borrador se persiste con contenido=""
    antes de iniciar el stream LLM, y el id se devuelve de inmediato.
    Sin esta validacion, el propietario podria publicar un borrador
    vacio/incompleto (incluido tras cancelar el stream). El use case
    PublicarBorrador lo levanta (422 en router).
    """


class FaltaCompetenciaError(DomainError):
    """El expediente no es competencia de la SAC (G5 gate bloqueante).

    EvaluadorCompetencia determina que la materia/territorio/grado del
    expediente no corresponde a la jurisdicción del Tribunal Supremo de
    Justicia Militar (Ley 1970 Arts. 2-4, CPPM Art. 400). GenerarBorrador
    lo levanta antes de generar un Auto de Vista/Dictamen para no emitir
    resolución sobre materia ajena. El router mapea a 422.
    """


class VarianteApelacionNoSoportadaError(DomainError):
    """El expediente es apelacion restringida y esa variante no tiene plantilla.

    La SAC SI es competente para la apelacion restringida (recurso contra
    sentencia; Ley 1970 Art. 3, CPPM Art. 400), pero la unica plantilla de
    apelacion existente es la de la incidental (recurso contra resolucion
    interlocutoria): su formula de POR TANTO resolveria otra cosa. Se falla
    con este error (422 en routers) en vez de emitir un documento con el
    grado equivocado.
    """


class RequisitosIncompletosError(DomainError):
    """Faltan obrados de entrada obligatorios para el tipo de caso.

    Vault sin sprints: taxonomia-documentos.md §A. El dictamen de
    radicatoria/auto de vista copia/analiza solo obrados; si no están
    cargados, la apertura debe alertar y el guard de generación lo frena.
    """

    def __init__(
        self,
        faltantes: set[str],
        tipo_proceso: str,
        tipo_respuesta: str | None = None,
    ) -> None:
        from src.domain.services.evaluador_requisitos import nombres_legibles

        self.faltantes = faltantes
        self.tipo_proceso = tipo_proceso
        self.tipo_respuesta = tipo_respuesta
        nombres = ", ".join(nombres_legibles(faltantes))
        if tipo_respuesta is not None:
            label = (
                "auto de vista"
                if tipo_respuesta.startswith("auto_vista")
                else "dictamen de radicatoria"
                if tipo_respuesta.startswith("dictamen")
                else tipo_respuesta
            )
            super().__init__(
                f"No se pudo generar el {label}. "
                f"Faltan obrados obligatorios para '{tipo_proceso}': {nombres}."
            )
        else:
            super().__init__(f"Faltan obrados obligatorios para '{tipo_proceso}': {nombres}.")
