"""Port: ObraRepo — Repositorio de obras (tabla `obra`).

Protocols (structural typing) — las implementaciones no necesitan heredar.

Sprint 4 (Regla 5 Trail of Bits BLOQUEANTE): el filtro de visibilidad
`must(expediente_id=X) AND must(propietario_id=user OR visibilidad=publicado)`
vive en el adapter (este puerto), NUNCA en el use case como parámetro
opcional. El use case siempre pasa `usuario_id`; el repo aplica el filtro.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.obra import Obra


class ObraRepo(Protocol):
    """Repositorio de obras (tabla `obra`)."""

    async def guardar(self, obra: Obra) -> Obra:
        """Inserta una obra. Devuelve entidad con id y created_at asignados."""
        ...

    async def obtener(self, obra_id: int, usuario_id: int) -> Obra | None:
        """Obtiene una obra por id aplicando Regla 5.

        Solo devuelve la obra si `propietario_id == usuario_id` OR
        `estado_visibilidad == 'publicado'`. None en cualquier otro caso
        (incluyendo obra inexistente — no se diferencia propositivamente
        para evitar information leak por timing/oracle).
        """
        ...

    async def obtener_global(self, obra_id: int) -> Obra | None:
        """Obtiene una obra por id SI es doctrina global activa.

        Solo `estado_visibilidad == 'global'` y `activo=true`. Es el acceso
        para `SeleccionarDoctrinaGlobal` (copiar una global al expediente o
        a la consulta). None en cualquier otro caso.
        """
        ...

    async def listar_por_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        solo_propias: bool = False,
    ) -> list[Obra]:
        """Lista obras de un expediente aplicando Regla 5.

        Filtro OBLIGATORIO: `expediente_id=X AND (propietario_id=user OR
        estado_visibilidad='publicado')`. Si `solo_propias=True`, además
        filtra por `propietario_id == usuario_id` (para vista supervisor
        de "mis obras subidas").
        """
        ...

    async def publicar(self, obra_id: int, propietario_id: int) -> Obra | None:
        """Cambia estado_visibilidad 'privado' -> 'publicado'.

        Valida propietario_id en el adapter (Regla 5: solo el dueño
        publica). Devuelve obra actualizada o None si el usuario no es
        el propietario.
        """
        ...

    async def marcar_promocion(
        self, obra_id: int, estado: str, motivo: str | None = None
    ) -> Obra | None:
        """Marca la promoción a jurisprudencia en `estado_validacion`
        (promocion_pendiente | promocion_rechazada). None si no existe."""
        ...

    async def promover_a_jurisprudencia(self, obra_id: int) -> Obra | None:
        """Aprueba la promoción: tipo 'jurisprudencia', visibilidad 'global',
        estado_validacion 'promovida'. None si no existe."""
        ...

    async def listar_promociones_pendientes(self) -> list[Obra]:
        """Obras activas con estado_validacion='promocion_pendiente'."""
        ...

    async def actualizar_estado_procesamiento(self, obra_id: int, estado: str) -> Obra | None:
        """Cambia estado_procesamiento (pendiente/procesando/completado/fallido).

        Para el flujo async de extracción PyMuPDF. Sin filtro de propietario
        —lo hace un worker interno, no el usuario.
        """
        ...

    async def eliminar(self, obra_id: int) -> bool:
        """Soft delete: marca `activo=false`. True si existía y estaba activa."""
        ...

    async def listar_global(
        self,
        usuario_id: int,
        solo_recomendadas: bool = False,
    ) -> list[Obra]:
        """Lista doctrinas globales activas (`estado_visibilidad='global'`).

        Regla de acceso: visibles para cualquier usuario autenticado (son
        jurisprudencia oficial compartida). Si `solo_recomendadas=True`,
        filtra por `recomendada=true` (sidebar futuro: solo recomendadas).
        """
        ...

    async def listar_por_estado(self, estado: str) -> list[Obra]:
        """Lista obras activas por estado de visibilidad (sin filtro de
        propietario). Para el supervisor: pendientes de aprobación
        ('publicado'), aprobadas ('global'), rechazadas. No expone contenido
        privado: solo la usa el flujo de aprobación de doctrina.
        """
        ...

    async def listar_doctrina_privada(
        self,
        expediente_id: int,
        usuario_id: int,
    ) -> list[Obra]:
        """Lista doctrinas privadas/publicadas del expediente (Regla 5).

        Filtro: `expediente_id=X AND (propietario_id=user OR
        estado_visibilidad='publicado') AND tipo_documento IN (doctrina,
        criterio)`. Para el desplegable "doctrina privada" del chat.
        """
        ...

    async def actualizar_visibilidad(
        self,
        obra_id: int,
        estado: str,
        motivo_rechazo: str | None = None,
    ) -> Obra | None:
        """Cambia estado_visibilidad (aprobación/rechazo de doctrina).

        Sin filtro de propietario: lo invoca el supervisor/admin (validación
        por rol en el use case). None si la obra no existe.
        """
        ...

    async def restaurar(
        self, obra_id: int, solicitante_id: int, *, es_supervisor: bool = False
    ) -> Obra | None:
        """Reactiva una obra soft-deleteada: `activo=true`.

        Solo el dueño, o el supervisor sobre doctrina publicada o global ajena. None si
        no existe o no tiene permiso (no se distingue, para no revelar que existe)."""
        ...

    async def registrar_origen(
        self,
        obra_id: int,
        obra_origen_id: int,
        copiada_por: int,
        sin_expediente: bool,
    ) -> None:
        """Registra trazabilidad de copia en `obra_origen` (Plan A)."""
        ...

    async def listar_criterios(self) -> list[Obra]:
        """Lista obras activas con `tipo_documento='criterio'` (módulo admin
        Criterios). Sin filtro de visibilidad: solo admin lo usa.
        """
        ...

    async def actualizar_criterio(
        self,
        obra_id: int,
        contenido_texto: str | None = None,
        procedencia: str | None = None,
        recomendada: bool | None = None,
    ) -> Obra | None:
        """Actualiza texto/metadatos de un criterio (módulo admin Criterios).
        None si la obra no existe o no es criterio.
        """
        ...

    async def obtener_por_ids(
        self,
        obra_ids: list[int],
        usuario_id: int,
    ) -> dict[int, Obra]:
        """Batch retrieve de obras aplicando Regla 5.

        Filtro: `WHERE id IN :ids AND (propietario_id = :uid OR
        estado_visibilidad = 'publicado')`.

        Sprint 5 (Regla 6): la ausencia de una obra en el dict resultante es
        la senal suficiente para que EvaluadorVisibilidad pode los fragmentos
        que la apuntan (la obra es privada ajena). Asi se evita N+1 en el
        adapter ExpansorJerarquico: un solo batch alimenta el evaluador.

        Returns:
            dict mapeando obra_id -> Obra. Obras privadas ajenas NO aparecen.
        """
        ...

    async def listar_mias(
        self,
        usuario_id: int,
        *,
        expediente_id: int | None = None,
        tipo_documento: str | None = None,
        estado: str | None = None,
        q: str | None = None,
        solo_recomendadas: bool = False,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
    ) -> list[Obra]:
        """Lista doctrinas del usuario (Plan C): privadas propias (de todos sus
        expedientes o uno específico) + copias de globales. Regla 5: solo
        `propietario_id == usuario_id`. Nunca privadas ajenas."""
        ...

    async def listar_estados(
        self,
        *,
        estado: str | None = None,
        q: str | None = None,
        tipo_documento: str | None = None,
        expediente_id: int | None = None,
    ) -> list[Obra]:
        """Lista doctrinas de revisión (Plan C, supervisor): pendientes
        ('publicado') y aprobadas ('global'), con origen. Sin filtro de
        propietario (las publicadas son de todos los operadores)."""
        ...

    async def actualizar_detalles(
        self,
        obra_id: int,
        propietario_id: int,
        *,
        es_supervisor: bool = False,
        nombre_archivo: str | None = None,
        autor: str | None = None,
        autor_instancia: str | None = None,
        fecha_documento: str | None = None,
        procedencia: str | None = None,
        recomendada: bool | None = None,
    ) -> Obra | None:
        """Edita detalles de una doctrina (Plan C). Solo el dueño (Regla 5) o el
        supervisor: este ultimo unicamente sobre doctrina publicada o global ajena
        (nunca privada ni rechazada). None si no existe o no tiene permiso."""
        ...

    async def eliminar_propia(
        self,
        obra_id: int,
        propietario_id: int,
    ) -> bool:
        """Soft delete de una doctrina privada propia (Plan C C2.6). Solo
        si `propietario_id == obra.propietario_id`. True si se eliminó."""

    async def existe_obra(
        self,
        expediente_id: int,
        tipo_documento: str,
        nombre_archivo: str,
    ) -> bool:
        """True si ya existe obra activa con ese expediente+tipo+nombre.

        Idempotencia del hook oficializar→ejemplo (N4): no duplica el
        ejemplo si el supervisor re-aprueba.
        """
        ...

    async def archivar_ejemplos_borrador(self, expediente_id: int, borrador_id: int) -> int:
        """Desactiva ejemplos N4 creados al oficializar un borrador.

        Al desoficializar, el ejemplo global dejaría de reflejar lo
        oficializado: se archiva (activo=false). Devuelve count.
        """
        ...

    async def tipos_activos_por_expediente(self, expediente_id: int) -> set[str]:
        """Tipos de obra activos del expediente (institucional, sin filtro propietario).

        Para validación de completitud (vault taxonomia A): el supervisor no ve
        privados del operador, pero la *existencia* de la pieza para el caso es
        metadato del expediente, no contenido privado. Solo tipos, nunca texto.
        """
        ...
