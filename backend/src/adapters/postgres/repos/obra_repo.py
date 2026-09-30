"""Repositorio PostgreSQL: ObraRepoImpl.

Implementa el puerto application.ports.obra_repo.ObraRepo.
Mapea la entidad de dominio Obra ↔ modelo ORM ObraModel.

Regla 5 Trail of Bits (BLOQUEANTE): el filtro de visibilidad
`must(expediente_id=X) AND must(propietario_id=user OR visibilidad=publicado)`
vive AQUÍ en el adapter. El use case siempre pasa `usuario_id`; este repo
lo aplica SIEMPRE. No es un parámetro opcional del caller.

Detalles de implementación:
- `obtener` y `listar_por_expediente` filtran por Regla 5 usando OR + AND.
- `publicar` valida propietario_id antes de cambiar visibilidad — si el
  caller no es el dueño, se devuelve None (404 para el router).
- `actualizar_estado_procesamiento` NO filtra por propietario — es
  invocado por el worker de extracción PyMuPDF, no por un usuario final.
"""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.obra import ObraModel
from src.application.ports.obra_repo import ObraRepo
from src.domain.entities.obra import Obra
from src.domain.services.validador_propietario import validar_usuario_id


class ObraRepoImpl(ObraRepo):
    """Implementación PostgreSQL del repositorio de obras."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, obra: Obra) -> Obra:
        """Inserta una obra. Devuelve entidad con id y created_at asignados."""
        model = ObraModel(
            expediente_id=obra.expediente_id,
            propietario_id=obra.propietario_id,
            tipo_documento=obra.tipo_documento,
            nombre_archivo=obra.nombre_archivo,
            contenido_texto=obra.contenido_texto,
            estado_visibilidad=obra.estado_visibilidad,
            fuente=obra.fuente,
            ruta_archivo=obra.ruta_archivo,
            fojas_inicio=obra.fojas_inicio,
            fojas_fin=obra.fojas_fin,
            tamano_archivo=obra.tamano_archivo,
            estado_procesamiento=obra.estado_procesamiento,
            autor_instancia=obra.autor_instancia,
            autor=obra.autor,
            fecha_documento=obra.fecha_documento,
            procedencia=obra.procedencia,
            estado_validacion=obra.estado_validacion,
            motivo_rechazo=obra.motivo_rechazo,
            recomendada=obra.recomendada,
            corpus=obra.corpus,
            corpus_ref=obra.corpus_ref,
            activo=obra.activo,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        obra.id = model.id
        obra.created_at = model.created_at
        return obra

    async def obtener(self, obra_id: int, usuario_id: int) -> Obra | None:
        """Obtiene una obra por id aplicando Regla 5.

        Devuelve la obra si `propietario_id == usuario_id` OR
        `estado_visibilidad in ('publicado', 'global')`. None en cualquier
        otro caso (incluyendo obra inexistente — no se diferencia
        propositivamente para evitar information leak por timing/oracle).
        """
        validar_usuario_id(usuario_id)

        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.activo.is_(True),
            or_(
                ObraModel.propietario_id == usuario_id,
                ObraModel.estado_visibilidad.in_(("publicado", "global")),
            ),
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def obtener_global(self, obra_id: int) -> Obra | None:
        """Obtiene una obra por id SI es doctrina global activa."""
        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.estado_visibilidad == "global",
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def listar_por_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        solo_propias: bool = False,
    ) -> list[Obra]:
        """Lista obras de un expediente aplicando Regla 5.

        Filtro OBLIGATORIO: `expediente_id=X AND (propietario_id=user OR
        estado_visibilidad='publicado')`. Si `solo_propias=True`, además
        filtra por `propietario_id == usuario_id` (vista supervisor de
        "mis obras subidas").
        """
        validar_usuario_id(usuario_id)

        condiciones_visibilidad = (
            [ObraModel.propietario_id == usuario_id]
            if solo_propias
            else [
                or_(
                    ObraModel.propietario_id == usuario_id,
                    ObraModel.estado_visibilidad == "publicado",
                )
            ]
        )

        stmt = select(ObraModel).where(
            ObraModel.expediente_id == expediente_id,
            ObraModel.activo.is_(True),
            *condiciones_visibilidad,
        )
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def publicar(self, obra_id: int, propietario_id: int) -> Obra | None:
        """Cambia estado_visibilidad 'privado' -> 'publicado'.

        Valida propietario_id en el adapter (Regla 5: solo el dueño
        publica). Devuelve obra actualizada o None si el usuario no es
        el propietario.
        """
        validar_usuario_id(propietario_id)

        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.propietario_id == propietario_id,
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado_visibilidad = "publicado"
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def _obra_activa(self, obra_id: int) -> ObraModel | None:
        stmt = select(ObraModel).where(ObraModel.id == obra_id, ObraModel.activo.is_(True))
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def marcar_promocion(
        self, obra_id: int, estado: str, motivo: str | None = None
    ) -> Obra | None:
        model = await self._obra_activa(obra_id)
        if model is None:
            return None
        model.estado_validacion = estado
        model.motivo_rechazo = motivo
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def promover_a_jurisprudencia(self, obra_id: int) -> Obra | None:
        model = await self._obra_activa(obra_id)
        if model is None:
            return None
        model.tipo_documento = "jurisprudencia"
        model.estado_visibilidad = "global"
        model.estado_validacion = "promovida"
        model.motivo_rechazo = None
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def listar_promociones_pendientes(self) -> list[Obra]:
        stmt = (
            select(ObraModel)
            .where(
                ObraModel.estado_validacion == "promocion_pendiente",
                ObraModel.activo.is_(True),
            )
            .order_by(ObraModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def actualizar_estado_procesamiento(self, obra_id: int, estado: str) -> Obra | None:
        """Cambia estado_procesamiento (pendiente/procesando/completado/fallido).

        Invocado por el worker de extracción PyMuPDF, no por un usuario
        final — sin filtro de propietario.
        """
        stmt = select(ObraModel).where(ObraModel.id == obra_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado_procesamiento = estado
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def eliminar(self, obra_id: int) -> bool:
        """Soft delete: marca `activo=false`. True si existía y estaba activa."""
        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.activo = False
        await self._session.flush()
        await self._session.commit()
        return True

    async def listar_global(
        self,
        usuario_id: int,
        solo_recomendadas: bool = False,
    ) -> list[Obra]:
        """Lista doctrinas globales activas (`estado_visibilidad='global'`)."""
        validar_usuario_id(usuario_id)

        condiciones = [
            ObraModel.estado_visibilidad == "global",
            ObraModel.activo.is_(True),
            # Los criterios son instrucciones de comportamiento (seed), NO
            # contribuciones que cargan/eligen supervisores y operadores.
            # Blacklist (!= criterio) y no whitelist (== doctrina): cualquier
            # otro tipo publicado a global debe seguir visible (bug fix tras
            # commit 71363d7, que varaba sentencias/autos aprobados).
            ObraModel.tipo_documento != "criterio",
        ]
        if solo_recomendadas:
            condiciones.append(ObraModel.recomendada.is_(True))

        stmt = select(ObraModel).where(*condiciones)
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def listar_por_estado(self, estado: str) -> list[Obra]:
        """Lista obras activas por estado de visibilidad (flujo de aprobación).

        Excluye criterios (tipo_documento='criterio'): el flujo de aprobacion
        es para contribuciones reales, no para instrucciones del asistente.
        """
        stmt = select(ObraModel).where(
            ObraModel.estado_visibilidad == estado,
            ObraModel.activo.is_(True),
            ObraModel.tipo_documento != "criterio",
        )
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def listar_doctrina_privada(
        self,
        expediente_id: int,
        usuario_id: int,
    ) -> list[Obra]:
        """Dropdown de material de referencia del expediente (Regla 5).

        Alcance: doctrina y material de referencia (doctrina legacy,
        material_caso, punteros doctrina_libro/jurisprudencia/ejemplo).
        Los criterios NO van aquí: tienen su propia gestión
        (/admin/criterios) y se inyectan automaticamente en la
        generacion via slot {{criterio_vocal}} — no son material
        seleccionable. Los obrados del expediente (sentencia, memorial,
        auto, ...) tampoco pertenecen: es material de consulta, no un
        listado general. Incluye punteros globales (expediente NULL con
        corpus) propios o publicados.
        """
        validar_usuario_id(usuario_id)

        stmt = select(ObraModel).where(
            or_(
                ObraModel.expediente_id == expediente_id,
                and_(
                    ObraModel.expediente_id.is_(None),
                    ObraModel.corpus.is_not(None),
                ),
            ),
            ObraModel.activo.is_(True),
            ObraModel.tipo_documento.in_(
                (
                    "doctrina",
                    "material_caso",
                    "doctrina_libro",
                    "jurisprudencia",
                    "ejemplo",
                )
            ),
            or_(
                ObraModel.propietario_id == usuario_id,
                ObraModel.estado_visibilidad == "publicado",
            ),
        )
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def actualizar_visibilidad(
        self,
        obra_id: int,
        estado: str,
        motivo_rechazo: str | None = None,
    ) -> Obra | None:
        """Cambia estado_visibilidad (aprobación/rechazo de doctrina)."""
        stmt = select(ObraModel).where(ObraModel.id == obra_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado_visibilidad = estado
        model.motivo_rechazo = motivo_rechazo
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def restaurar(
        self, obra_id: int, solicitante_id: int, *, es_supervisor: bool = False
    ) -> Obra | None:
        """Reactiva una obra soft-deleteada: `activo=true`.

        Solo el dueño (Regla 5), o el supervisor sobre doctrina publicada o global ajena.
        """
        validar_usuario_id(solicitante_id)
        stmt = select(ObraModel).where(ObraModel.id == obra_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None
        if model.propietario_id != solicitante_id and not (
            es_supervisor and model.estado_visibilidad in ("publicado", "global")
        ):
            return None

        model.activo = True
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def registrar_origen(
        self,
        obra_id: int,
        obra_origen_id: int,
        copiada_por: int,
        sin_expediente: bool,
    ) -> None:
        """Registra trazabilidad de copia en `obra_origen` (Plan A)."""
        from src.adapters.postgres.models.obra_origen import ObraOrigenModel

        self._session.add(
            ObraOrigenModel(
                obra_id=obra_id,
                obra_origen_id=obra_origen_id,
                copiada_por=copiada_por,
                sin_expediente=sin_expediente,
            )
        )
        await self._session.commit()

    async def listar_criterios(self) -> list[Obra]:
        """Lista obras activas con `tipo_documento='criterio'` (admin Criterios)."""
        stmt = select(ObraModel).where(
            ObraModel.tipo_documento == "criterio",
            ObraModel.activo.is_(True),
        )
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def actualizar_criterio(
        self,
        obra_id: int,
        contenido_texto: str | None = None,
        procedencia: str | None = None,
        recomendada: bool | None = None,
    ) -> Obra | None:
        """Actualiza texto/metadatos de un criterio (admin Criterios)."""
        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.tipo_documento == "criterio",
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        if contenido_texto is not None:
            model.contenido_texto = contenido_texto
        if procedencia is not None:
            model.procedencia = procedencia
        if recomendada is not None:
            model.recomendada = recomendada

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def obtener_por_ids(
        self,
        obra_ids: list[int],
        usuario_id: int,
    ) -> dict[int, Obra]:
        """Batch retrieve de obras aplicando Regla 5 (propias + publicadas).

        Filtro: `WHERE id IN :ids AND (propietario_id = :uid OR estado_visibilidad = 'publicado')`.

        Sprint 5 (Regla 6): la ausencia de una obra en el dict resultante es
        la senal para que EvaluadorVisibilidad pode los fragmentos que la
        apuntan (la obra es privada ajena). Asi se evita N+1: un solo batch
        alimenta al evaluador.

        Returns:
            dict mapeando obra_id -> Obra. Obras privadas ajenas NO aparecen.
        """
        if not obra_ids:
            return {}

        validar_usuario_id(usuario_id)

        stmt = select(ObraModel).where(
            ObraModel.id.in_(obra_ids),
            ObraModel.activo.is_(True),
            or_(
                ObraModel.propietario_id == usuario_id,
                ObraModel.estado_visibilidad.in_(("publicado", "global")),
            ),
        )
        result = await self._session.execute(stmt)
        modelos = result.scalars().all()
        return {m.id: self._to_domain(m) for m in modelos}

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
        """Lista doctrinas del usuario (Plan C): privadas propias de todos sus
        expedientes (o uno específico) + copias de globales."""
        validar_usuario_id(usuario_id)

        condiciones = [
            ObraModel.propietario_id == usuario_id,
            ObraModel.activo.is_(True),
            # Excluir criterios: son instrucciones de comportamiento y se
            # gestionan en /admin/criterios, no como biblioteca personal.
            # Blacklist para no varar otros tipos propios del usuario.
            ObraModel.tipo_documento != "criterio",
        ]
        if expediente_id is not None:
            condiciones.append(ObraModel.expediente_id == expediente_id)
        if tipo_documento is not None:
            condiciones.append(ObraModel.tipo_documento == tipo_documento)
        if estado is not None:
            condiciones.append(ObraModel.estado_visibilidad == estado)
        if solo_recomendadas:
            condiciones.append(ObraModel.recomendada.is_(True))
        if q:
            condiciones.append(ObraModel.nombre_archivo.ilike(f"%{q}%"))
        if fecha_desde:
            condiciones.append(ObraModel.created_at >= fecha_desde)
        if fecha_hasta:
            condiciones.append(ObraModel.created_at <= fecha_hasta)

        stmt = select(ObraModel).where(*condiciones)
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def listar_estados(
        self,
        *,
        estado: str | None = None,
        q: str | None = None,
        tipo_documento: str | None = None,
        expediente_id: int | None = None,
    ) -> list[Obra]:
        """Lista doctrinas de revisión (supervisor, Plan C): pendientes
        ('publicado') y aprobadas ('global'). Sin filtro de propietario.
        Excluye criterios (instrucciones del asistente, no doctrina)."""
        condiciones = [
            ObraModel.activo.is_(True),
            ObraModel.tipo_documento != "criterio",
        ]
        if estado is not None:
            condiciones.append(ObraModel.estado_visibilidad == estado)
        else:
            condiciones.append(ObraModel.estado_visibilidad.in_(("publicado", "global")))
        if tipo_documento is not None:
            condiciones.append(ObraModel.tipo_documento == tipo_documento)
        if expediente_id is not None:
            condiciones.append(ObraModel.expediente_id == expediente_id)
        if q:
            condiciones.append(ObraModel.nombre_archivo.ilike(f"%{q}%"))

        stmt = select(ObraModel).where(*condiciones)
        stmt = stmt.order_by(ObraModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

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
        supervisor sobre doctrina publicada o global ajena; el operador no puede
        tocar la de otros (tiene `doctrina:actualizar`, asi que el permiso solo no basta)."""
        validar_usuario_id(propietario_id)

        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        # Regla 5: solo el dueño; el supervisor ademas las publicadas/globales ajenas
        # (nunca las privadas ni rechazadas de otro).
        if model.propietario_id != propietario_id and not (
            es_supervisor and model.estado_visibilidad in ("publicado", "global")
        ):
            return None

        if nombre_archivo is not None:
            model.nombre_archivo = nombre_archivo
        if autor is not None:
            model.autor = autor
        if autor_instancia is not None:
            model.autor_instancia = autor_instancia
        if fecha_documento is not None:
            model.fecha_documento = fecha_documento
        if procedencia is not None:
            model.procedencia = procedencia
        if recomendada is not None:
            model.recomendada = recomendada

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def eliminar_propia(
        self,
        obra_id: int,
        propietario_id: int,
    ) -> bool:
        """Soft delete de una doctrina privada propia (Plan C). Solo si el
        usuario es el propietario."""
        validar_usuario_id(propietario_id)

        stmt = select(ObraModel).where(
            ObraModel.id == obra_id,
            ObraModel.activo.is_(True),
            ObraModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.activo = False
        await self._session.flush()
        await self._session.commit()
        return True

    async def existe_obra(
        self,
        expediente_id: int,
        tipo_documento: str,
        nombre_archivo: str,
    ) -> bool:
        """True si ya existe obra activa con ese expediente+tipo+nombre."""
        stmt = select(
            exists().where(
                ObraModel.expediente_id == expediente_id,
                ObraModel.tipo_documento == tipo_documento,
                ObraModel.nombre_archivo == nombre_archivo,
                ObraModel.activo.is_(True),
            )
        )
        result = await self._session.execute(stmt)
        return bool(result.scalar())

    async def archivar_ejemplos_borrador(self, expediente_id: int, borrador_id: int) -> int:
        """Desactiva ejemplos N4 creados al oficializar un borrador."""
        stmt = select(ObraModel).where(
            ObraModel.expediente_id == expediente_id,
            ObraModel.tipo_documento == "ejemplo",
            ObraModel.nombre_archivo.like(f"ejemplo_borrador_{borrador_id}\\_%"),
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        count = 0
        for model in result.scalars().all():
            model.activo = False
            count += 1
        if count:
            await self._session.flush()
            await self._session.commit()
        return count

    async def tipos_activos_por_expediente(self, expediente_id: int) -> set[str]:
        """Tipos activos del expediente (institucional, sin Regla 5). Solo tipos."""
        from sqlalchemy import distinct

        stmt = select(distinct(ObraModel.tipo_documento)).where(
            ObraModel.expediente_id == expediente_id,
            ObraModel.activo.is_(True),
        )
        result = await self._session.execute(stmt)
        return {r[0] for r in result.all() if r[0] is not None}

    def _to_domain(self, model: ObraModel) -> Obra:
        return Obra(
            id=model.id,
            expediente_id=model.expediente_id,
            propietario_id=model.propietario_id,
            tipo_documento=model.tipo_documento,
            nombre_archivo=model.nombre_archivo,
            contenido_texto=model.contenido_texto,
            ruta_archivo=model.ruta_archivo,
            fojas_inicio=model.fojas_inicio,
            fojas_fin=model.fojas_fin,
            estado_visibilidad=model.estado_visibilidad,
            fuente=model.fuente,
            tamano_archivo=model.tamano_archivo,
            estado_procesamiento=model.estado_procesamiento,
            autor_instancia=model.autor_instancia,
            created_at=model.created_at,
            autor=model.autor,
            fecha_documento=model.fecha_documento,
            procedencia=model.procedencia,
            estado_validacion=model.estado_validacion,
            motivo_rechazo=model.motivo_rechazo,
            recomendada=model.recomendada,
            corpus=model.corpus,
            corpus_ref=model.corpus_ref,
            activo=model.activo,
        )


def get_obra_repo(session: AsyncSession) -> ObraRepo:
    """Factory para inyección de dependencias."""
    return ObraRepoImpl(session)
