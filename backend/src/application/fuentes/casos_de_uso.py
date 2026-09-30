"""Flujo común de fuentes: privada -> pendiente -> global (con aprobación).

Normas, jurisprudencia y doctrina (libros) viven en la tabla `norma` y comparten el
flujo de las obras de doctrina: el operador sube una fuente privada, la propone y
el supervisor la aprueba (o la rechaza con motivo). El supervisor puede cargar
directo a global. Los puntos de Qdrant siguen el estado (`visibilidad`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.fuentes.abreviatura import generar_abreviatura
from src.application.services.trabajos_indexado import TokenCancelacion
from src.domain.services.categoria_fuente import categoria_de_jerarquia, categoria_de_obra

log = logging.getLogger(__name__)

_SUBGRUPO_JURISPRUDENCIA = {"scp_tcp": "tcp", "sentencia_cidh": "cidh"}


class FuenteNoEncontradaError(LookupError):
    """La fuente no existe o está inactiva."""


class FuenteNoPropiaError(PermissionError):
    """Solo el propietario puede proponer su fuente."""


class TransicionInvalidaError(ValueError):
    """El estado actual no permite esa transición."""


@dataclass(frozen=True, slots=True)
class FuenteResumen:
    id: int
    abreviatura: str
    nombre: str
    categoria: str
    subgrupo: str | None  # jurisprudencia: tcp | cidh
    estado_visibilidad: str
    propietario_id: int | None
    es_propia: bool
    motivo_rechazo: str | None = None


def _resumen(n, usuario_id: int | None) -> FuenteResumen:
    categoria = categoria_de_jerarquia(n.jerarquia)
    return FuenteResumen(
        id=n.id,
        abreviatura=n.abreviatura,
        nombre=n.nombre,
        categoria=categoria,
        subgrupo=_SUBGRUPO_JURISPRUDENCIA.get(n.tipo) if categoria == "jurisprudencia" else None,
        estado_visibilidad=n.estado_visibilidad,
        propietario_id=n.propietario_id,
        es_propia=n.propietario_id is not None and n.propietario_id == usuario_id,
        motivo_rechazo=n.motivo_rechazo,
    )


async def _sincronizar(vectores: dict, categoria: str, norma_id: int, payload: dict) -> None:
    """Best-effort: PG ya cambió; si Qdrant falla se registra y no se revierte."""
    try:
        await vectores[categoria].actualizar_payload_norma(norma_id, payload)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo sincronizar la fuente %s en Qdrant", norma_id)


class ListarFuentes:
    """Lo global, lo propio y —para el supervisor— las pendientes de aprobación."""

    def __init__(self, norma_repo) -> None:
        self._norma_repo = norma_repo

    async def ejecutar(
        self, categoria: str, *, usuario_id: int, es_supervisor: bool
    ) -> list[FuenteResumen]:
        fuentes = []
        for n in await self._norma_repo.list_all():
            if not (n.activo and n.indexado) or categoria_de_jerarquia(n.jerarquia) != categoria:
                continue
            visible = (
                n.estado_visibilidad == "global"
                or n.propietario_id == usuario_id
                or (es_supervisor and n.estado_visibilidad == "pendiente")
            )
            if visible:
                fuentes.append(_resumen(n, usuario_id))
        return sorted(fuentes, key=lambda f: f.nombre)

    async def pendientes(self, *, usuario_id: int) -> list[FuenteResumen]:
        """Cola del supervisor: todas las fuentes pendientes de aprobación."""
        return [
            _resumen(n, usuario_id)
            for n in await self._norma_repo.list_all()
            if n.activo and n.indexado and n.estado_visibilidad == "pendiente"
        ]


class SubirFuente:
    """El operador sube privado; el supervisor, directo a global."""

    def __init__(self, indexar_norma: IndexarNorma, norma_repo) -> None:
        self._indexar = indexar_norma
        self._norma_repo = norma_repo

    async def ejecutar(
        self,
        *,
        categoria: str,
        nombre: str,
        ruta: str | Path,
        usuario_id: int,
        es_supervisor: bool,
        texto: str | None = None,
        tipo: str | None = None,
        jerarquia: str | None = None,
        token: TokenCancelacion | None = None,
    ):
        abreviatura = await generar_abreviatura(categoria, nombre, self._norma_repo)
        return await self._indexar.ejecutar(
            IndexarNormaRequest(
                abreviatura=abreviatura,
                ruta_pdf=Path(ruta),
                texto_directo=texto,
                indexado_por=usuario_id,
                categoria=categoria,
                nombre=nombre,
                tipo=tipo,
                jerarquia=jerarquia,
                propietario_id=usuario_id,
                estado_visibilidad="global" if es_supervisor else "privado",
            ),
            token=token,
        )


class PromoverObraANorma:
    """Un obrado publicado pasa a ser una norma del corpus.

    Se indexa por artículos como una fuente de la categoría `norma`, con el mismo
    flujo: el operador la deja `pendiente` (la aprueba el supervisor en la cola
    común) y el supervisor puede promover directo a `global`. El obrado queda
    intacto y la norma guarda su `origen_obra_id`.
    """

    def __init__(self, indexar_norma: IndexarNorma, norma_repo, obra_repo) -> None:
        self._indexar = indexar_norma
        self._norma_repo = norma_repo
        self._obra_repo = obra_repo

    async def validar(self, *, obra_id: int, usuario_id: int, es_supervisor: bool):
        """Checks previos, sin indexar: para validar sincronico antes de encolar.

        Separado de `indexar` para que el router pueda `await validar(...)`
        (404/403/409/422 inmediatos) y recien despues encolar la parte lenta
        (`indexar`) como trabajo cancelable.
        """
        obra = await self._obra_repo.obtener(obra_id, usuario_id)
        if obra is None:
            raise FuenteNoEncontradaError(f"Obra id={obra_id} no encontrada.")
        if not es_supervisor and obra.propietario_id != usuario_id:
            raise FuenteNoPropiaError("Solo el propietario promueve su obrado a norma.")
        if categoria_de_obra(obra.tipo_documento) != "obrado":
            raise TransicionInvalidaError("Solo un obrado del expediente puede promoverse.")
        if obra.estado_visibilidad != "publicado":
            raise TransicionInvalidaError("El obrado debe estar publicado antes de promoverse.")
        if obra.estado_validacion == "promovida_a_norma":
            raise TransicionInvalidaError("El obrado ya fue promovido a norma.")
        if not (obra.contenido_texto or "").strip():
            raise TransicionInvalidaError("El obrado no tiene texto para indexar.")
        return obra

    async def indexar(
        self,
        obra,
        *,
        obra_id: int,
        usuario_id: int,
        es_supervisor: bool,
        nombre: str,
        jerarquia: str,
        token: TokenCancelacion | None = None,
    ):
        """Indexa un `obra` ya validado por `validar`. Es la parte lenta: la
        llama el router directo (`ejecutar`) o el trabajo encolado."""
        abreviatura = await generar_abreviatura("norma", nombre, self._norma_repo)
        resultado = await self._indexar.ejecutar(
            IndexarNormaRequest(
                abreviatura=abreviatura,
                ruta_pdf=Path(obra.nombre_archivo),
                texto_directo=obra.contenido_texto,
                indexado_por=usuario_id,
                categoria="norma",
                nombre=nombre,
                jerarquia=jerarquia,
                propietario_id=obra.propietario_id,
                estado_visibilidad="global" if es_supervisor else "pendiente",
                origen_obra_id=obra_id,
            ),
            token=token,
        )
        await self._obra_repo.marcar_promocion(obra_id, "promovida_a_norma")
        return resultado

    async def ejecutar(
        self,
        *,
        obra_id: int,
        usuario_id: int,
        es_supervisor: bool,
        nombre: str,
        jerarquia: str,
        token: TokenCancelacion | None = None,
    ):
        obra = await self.validar(
            obra_id=obra_id, usuario_id=usuario_id, es_supervisor=es_supervisor
        )
        return await self.indexar(
            obra,
            obra_id=obra_id,
            usuario_id=usuario_id,
            es_supervisor=es_supervisor,
            nombre=nombre,
            jerarquia=jerarquia,
            token=token,
        )


class _Base:
    def __init__(self, norma_repo, vectores: dict) -> None:
        self._norma_repo = norma_repo
        self._vectores = vectores

    async def _obtener(self, fuente_id: int):
        norma = await self._norma_repo.get_by_id(fuente_id)
        if norma is None or not norma.activo:
            raise FuenteNoEncontradaError(f"Fuente id={fuente_id} no encontrada.")
        return norma


class ProponerFuente(_Base):
    """El dueño propone su fuente privada: queda pendiente de aprobación."""

    async def ejecutar(self, *, fuente_id: int, usuario_id: int) -> FuenteResumen:
        norma = await self._obtener(fuente_id)
        if norma.propietario_id != usuario_id:
            raise FuenteNoPropiaError("Solo el propietario propone su fuente.")
        if norma.estado_visibilidad != "privado":
            raise TransicionInvalidaError(
                f"No se puede proponer una fuente en estado {norma.estado_visibilidad!r}."
            )
        actualizada = await self._norma_repo.actualizar_visibilidad(fuente_id, "pendiente", None)
        await _sincronizar(
            self._vectores,
            categoria_de_jerarquia(norma.jerarquia),
            fuente_id,
            {"visibilidad": "pendiente"},
        )
        return _resumen(actualizada, usuario_id)


class ResolverFuente(_Base):
    """El supervisor aprueba (a global) o rechaza con motivo."""

    async def ejecutar(
        self, *, fuente_id: int, aprobar: bool, motivo: str | None = None
    ) -> FuenteResumen:
        if not aprobar and not motivo:
            raise ValueError("El motivo es obligatorio para rechazar.")
        norma = await self._obtener(fuente_id)
        if norma.estado_visibilidad not in ("pendiente", "privado"):
            raise TransicionInvalidaError(
                f"No se puede resolver una fuente en estado {norma.estado_visibilidad!r}."
            )
        estado = "global" if aprobar else "rechazado"
        actualizada = await self._norma_repo.actualizar_visibilidad(
            fuente_id, estado, None if aprobar else motivo
        )
        if aprobar:
            await _sincronizar(
                self._vectores,
                categoria_de_jerarquia(norma.jerarquia),
                fuente_id,
                {"visibilidad": "global"},
            )
        return _resumen(actualizada, None)
