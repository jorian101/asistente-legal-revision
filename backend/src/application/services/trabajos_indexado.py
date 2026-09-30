"""Trabajos de indexado en curso: estado y cancelacion.

El indexado (extraer + segmentar + embeber + upsert) tarda minutos y corre
dentro de la request, asi que hasta ahora no habia forma de interrumpirlo.
Aca vive el estado de cada trabajo y la bandera con la que el caso de uso se
entera de que lo cancelaron.

Cancelacion cooperativa a proposito: NO usamos `task.cancel()`. Abortar a
mitad de una escritura (flush de fragmentos, upsert a Qdrant) dejaria la base
a medias. El caso de uso llama a `verificar()` en los puntos de control y se
detiene ahi; la demora de la cancelacion es la de la fase en curso (segmentar
un PDF grande es lo mas lento).

Lo que el trabajo alcanzo a escribir lo deshace el propio caso de uso: registra
un callback con `al_cancelar(...)` y este modulo lo ejecuta al cerrar el
trabajo.

ponytail: registro en memoria y por proceso. Alcance: un solo worker de uvicorn
(el setup local corre uno) y se pierde al reiniciar. Con varios workers o
reinicios haria falta respaldarlo en la base o en un servicio; hoy no se
justifica.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum

log = logging.getLogger(__name__)

# Cuantos trabajos terminados se conservan para poder consultar su estado.
_MAX_TERMINADOS = 50


class IndexadoCanceladoError(Exception):
    """El usuario cancelo el trabajo. Se lanza desde el punto de control."""


class TokenCancelacion:
    """Bandera cooperativa de cancelacion + limpieza de lo ya escrito.

    El caso de uso llama a `verificar()` entre fases y registra con
    `al_cancelar()` como deshacer lo que haya escrito.
    """

    __slots__ = ("_cancelado", "_limpiezas")

    def __init__(self) -> None:
        self._cancelado = False
        self._limpiezas: list[Callable[[], Awaitable[None]]] = []

    @property
    def cancelado(self) -> bool:
        return self._cancelado

    def cancelar(self) -> None:
        """Marca el trabajo como cancelado (lo llama el endpoint)."""
        self._cancelado = True

    def verificar(self) -> None:
        """Corta el trabajo si lo cancelaron. Llamar en cada punto de control."""
        if self._cancelado:
            raise IndexadoCanceladoError("El trabajo fue cancelado.")

    def al_cancelar(self, limpieza: Callable[[], Awaitable[None]]) -> None:
        """Registra como deshacer lo escrito hasta aca. Se ejecuta en LIFO."""
        self._limpiezas.append(limpieza)

    async def limpiar(self) -> None:
        """Ejecuta las limpiezas registradas, de la mas nueva a la mas vieja.

        Una limpieza que falla no frena a las demas: se loguea y se sigue.
        """
        while self._limpiezas:
            limpieza = self._limpiezas.pop()
            try:
                await limpieza()
            except Exception:
                log.exception("Fallo la limpieza de un trabajo de indexado cancelado")


class EstadoJob(StrEnum):
    EN_CURSO = "en_curso"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"
    ERROR = "error"


@dataclass
class Job:
    """Un trabajo de indexado, en curso o terminado."""

    id: str
    tipo: str
    usuario_id: int
    token: TokenCancelacion
    iniciado_en: datetime
    estado: EstadoJob = EstadoJob.EN_CURSO
    terminado_en: datetime | None = None
    error: str | None = None
    resultado: object | None = None
    tarea: asyncio.Task | None = field(default=None, repr=False)


class JobInexistenteError(Exception):
    """No hay ningun trabajo con ese id."""


class JobYaTerminadoError(Exception):
    """El trabajo ya termino: no hay nada que cancelar."""


class CancelacionNoPermitidaError(Exception):
    """Solo quien lanzo el trabajo o un administrador puede cancelarlo."""


def estado_publico(job: Job) -> dict:
    """Representacion serializable del trabajo para la API."""
    resultado = job.resultado
    if is_dataclass(resultado) and not isinstance(resultado, type):
        resultado = asdict(resultado)
    return {
        "id": job.id,
        "tipo": job.tipo,
        "estado": job.estado.value,
        # Pedida != detenido: el trabajo se corta en el proximo punto de control.
        "cancelacion_solicitada": job.token.cancelado,
        "iniciado_en": job.iniciado_en.isoformat(),
        "terminado_en": job.terminado_en.isoformat() if job.terminado_en else None,
        "error": job.error,
        "resultado": resultado,
    }


class RegistroTrabajos:
    """Registro de trabajos en memoria. Una instancia por proceso."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def lanzar(
        self,
        *,
        tipo: str,
        usuario_id: int,
        fabrica: Callable[[TokenCancelacion], Awaitable[object]],
    ) -> Job:
        """Arranca el trabajo en segundo plano y devuelve su estado.

        `fabrica(token)` construye la corrutina del caso de uso con el token
        ya cableado, para que se entere si lo cancelan.
        """
        self._podar()
        job = Job(
            id=uuid.uuid4().hex,
            tipo=tipo,
            usuario_id=usuario_id,
            token=TokenCancelacion(),
            iniciado_en=datetime.now(UTC),
        )
        job.tarea = asyncio.create_task(self._correr(job, fabrica(job.token)))
        self._jobs[job.id] = job
        return job

    def obtener(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancelar(self, job_id: str, *, usuario_id: int, es_admin: bool) -> Job:
        """Marca el trabajo para que se detenga en el proximo punto de control."""
        job = self._jobs.get(job_id)
        if job is None:
            raise JobInexistenteError(job_id)
        if job.estado is not EstadoJob.EN_CURSO:
            raise JobYaTerminadoError(f"El trabajo ya termino ({job.estado.value}).")
        if job.usuario_id != usuario_id and not es_admin:
            raise CancelacionNoPermitidaError(
                "Solo quien lanzo el trabajo o un administrador puede cancelarlo."
            )
        job.token.cancelar()
        return job

    async def _correr(self, job: Job, corrutina: Awaitable[object]) -> None:
        try:
            job.resultado = await corrutina
            job.estado = EstadoJob.COMPLETADO
        except IndexadoCanceladoError as exc:
            job.error = str(exc)
            await job.token.limpiar()
            job.estado = EstadoJob.CANCELADO
        except asyncio.CancelledError:
            await job.token.limpiar()
            job.estado = EstadoJob.CANCELADO
            raise
        except Exception as exc:
            job.error = str(exc)
            job.estado = EstadoJob.ERROR
            log.exception("Trabajo de indexado %s fallo", job.id)
        finally:
            job.terminado_en = datetime.now(UTC)
            job.tarea = None

    def _podar(self) -> None:
        """Descarta los terminados mas viejos para no crecer sin limite."""
        terminados = [j for j in self._jobs.values() if j.estado is not EstadoJob.EN_CURSO]
        if len(terminados) < _MAX_TERMINADOS:
            return
        terminados.sort(key=lambda j: j.terminado_en or j.iniciado_en)
        for job in terminados[: len(terminados) - _MAX_TERMINADOS + 1]:
            self._jobs.pop(job.id, None)


# Instancia del proceso. La usan los routers para encolar y cancelar.
registro = RegistroTrabajos()
