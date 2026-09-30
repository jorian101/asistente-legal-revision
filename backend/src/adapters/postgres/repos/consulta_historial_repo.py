"""Repositorio PostgreSQL: ConsultaHistorialRepo.

Implementa el puerto application.ports.ConsultaHistorialRepo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.consulta_historial import (
    ConsultaHistorialModel,
)
from src.adapters.postgres.models.usuario import UsuarioModel
from src.application.ports.consulta_historial_repo import (
    ConsultaHistorialAdmin,
    ConsultaHistorialRepo,
    DashboardResumen,
    ResumenDia,
    ResumenModelo,
    ResumenTipo,
    ResumenUsuario,
)
from src.domain.entities.consulta_historial import ConsultaHistorial


class ConsultaHistorialRepoImpl(ConsultaHistorialRepo):
    """Implementacion PostgreSQL del historial de consultas RAG."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, historial: ConsultaHistorial) -> ConsultaHistorial:
        """Inserta un registro de consulta."""
        model = ConsultaHistorialModel(
            expediente_id=historial.expediente_id,
            usuario_id=historial.usuario_id,
            pregunta=historial.pregunta,
            respuesta=historial.respuesta,
            tipo_respuesta=historial.tipo_respuesta,
            fuentes_recuperadas=historial.fuentes_recuperadas,
            latencia_ms=historial.latencia_ms,
            modelo_llm=historial.modelo_llm,
            estado=historial.estado or "en_progreso",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        # Commit explicito: SQLAlchemy 2.0 AsyncSession NO autocommitea
        # al salir de `async with` en get_db_session. Sin esto, el INSERT
        # se pierde en el rollback del request. Patron de seed_usuarios.py
        # e ingest_corpus.py (ver test_ingestion/test_explicit_commit.py).
        await self._session.commit()

        historial.id = model.id
        historial.created_at = model.created_at
        return historial

    async def listar_por_usuario(
        self,
        usuario_id: int,
        expediente_id: int | None,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorial], int]:
        """Lista el historial del usuario (Regla 4: solo el suyo)."""
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool) or usuario_id <= 0:
            raise ValueError("usuario_id es obligatorio y debe ser int > 0 (Regla 4).")

        base = select(ConsultaHistorialModel).where(ConsultaHistorialModel.usuario_id == usuario_id)
        base = base.where(ConsultaHistorialModel.activo == True)  # noqa: E712 — soft delete CRITICAL #4
        if expediente_id is not None:
            base = base.where(ConsultaHistorialModel.expediente_id == expediente_id)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(ConsultaHistorialModel.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def listar_todas(
        self,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorial], int]:
        """Lista todo el historial (solo admin, HU-22 metricas contexto)."""
        base = select(ConsultaHistorialModel).where(
            ConsultaHistorialModel.activo == True  # noqa: E712
        )

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(ConsultaHistorialModel.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    async def actualizar_respuesta(
        self,
        historial_id: int,
        respuesta: str,
        modelo_llm: str,
    ) -> ConsultaHistorial | None:
        """Actualiza respuesta + modelo_llm post-LLM stream (Sprint 6)."""
        stmt = select(ConsultaHistorialModel).where(ConsultaHistorialModel.id == historial_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.respuesta = respuesta
        model.modelo_llm = modelo_llm
        model.estado = "completado"
        await self._session.flush()
        await self._session.commit()
        return self._to_domain(model)

    async def actualizar_respuesta_parcial(
        self,
        historial_id: int,
        respuesta: str,
    ) -> None:
        """P1: persiste el parcial acumulado sin tocar `estado` (sigue en_progreso)."""
        stmt = select(ConsultaHistorialModel).where(ConsultaHistorialModel.id == historial_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return

        model.respuesta = respuesta
        await self._session.flush()
        await self._session.commit()

    async def marcar_error(self, historial_id: int) -> bool:
        """Marca una consulta como 'error' (pipeline fallo sin respuesta)."""
        stmt = select(ConsultaHistorialModel).where(ConsultaHistorialModel.id == historial_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.estado = "error"
        await self._session.flush()
        await self._session.commit()
        return True

    async def marcar_error_antiguos(self, minutos: int = 30) -> int:
        """Marca 'error' las consultas en_progreso más viejas que X minutos.

        Reconciliación al arranque: un reinicio con productores vivos los
        deja colgados para siempre. Best-effort para lifespan.
        """
        from sqlalchemy import update

        limite = datetime.now(UTC) - timedelta(minutes=minutos)
        stmt = (
            update(ConsultaHistorialModel)
            .where(
                or_(
                    ConsultaHistorialModel.estado.is_(None),
                    ConsultaHistorialModel.estado == "en_progreso",
                ),
                ConsultaHistorialModel.created_at < limite,
            )
            .values(estado="error")
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return int(result.rowcount or 0)

    async def obtener_por_id(
        self,
        historial_id: int,
        usuario_id: int,
    ) -> ConsultaHistorial | None:
        """Entrada por id SOLO si pertenece al usuario y esta activa (Regla 4)."""
        stmt = select(ConsultaHistorialModel).where(
            ConsultaHistorialModel.id == historial_id,
            ConsultaHistorialModel.usuario_id == usuario_id,
            ConsultaHistorialModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def actualizar_metadatos(
        self,
        historial_id: int,
        *,
        tipo_respuesta: str | None,
        fuentes_recuperadas: dict | None,
        latencia_ms: int | None,
    ) -> ConsultaHistorial | None:
        """Actualiza tipo_respuesta + fuentes + latencia post-pipeline (Task A)."""
        stmt = select(ConsultaHistorialModel).where(ConsultaHistorialModel.id == historial_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        if tipo_respuesta is not None:
            model.tipo_respuesta = tipo_respuesta
        if fuentes_recuperadas is not None:
            model.fuentes_recuperadas = fuentes_recuperadas
        if latencia_ms is not None:
            model.latencia_ms = latencia_ms
        await self._session.flush()
        await self._session.commit()
        return self._to_domain(model)

    async def eliminar_soft(
        self,
        historial_id: int,
        usuario_id: int,
    ) -> bool:
        """Soft delete: activo=False SOLO si la entrada es del usuario (Regla 4)."""
        stmt = select(ConsultaHistorialModel).where(
            ConsultaHistorialModel.id == historial_id,
            ConsultaHistorialModel.usuario_id == usuario_id,
            ConsultaHistorialModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.activo = False
        await self._session.flush()
        await self._session.commit()
        return True

    async def listar_admin(
        self,
        *,
        usuario_id: int | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
        estado: str | None,
        fecha_desde: datetime | None,
        fecha_hasta: datetime | None,
        texto: str | None,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorialAdmin], int]:
        """Lista todo el historial con filtros (solo admin, join a usuario)."""
        base = (
            select(ConsultaHistorialModel, UsuarioModel.carnet, UsuarioModel.nombre)
            .join(UsuarioModel, UsuarioModel.id == ConsultaHistorialModel.usuario_id)
            .where(ConsultaHistorialModel.activo == True)  # noqa: E712
        )
        if usuario_id is not None:
            base = base.where(ConsultaHistorialModel.usuario_id == usuario_id)
        if expediente_id is not None:
            base = base.where(ConsultaHistorialModel.expediente_id == expediente_id)
        if tipo_respuesta is not None:
            base = base.where(ConsultaHistorialModel.tipo_respuesta == tipo_respuesta)
        if estado == "en_progreso":
            base = base.where(
                or_(
                    ConsultaHistorialModel.estado.is_(None),
                    ConsultaHistorialModel.estado == "en_progreso",
                )
            )
        elif estado in {"terminadas", "completado"}:
            base = base.where(ConsultaHistorialModel.estado == "completado")
        elif estado == "error":
            base = base.where(ConsultaHistorialModel.estado == "error")
        if fecha_desde is not None:
            base = base.where(ConsultaHistorialModel.created_at >= fecha_desde)
        if fecha_hasta is not None:
            base = base.where(ConsultaHistorialModel.created_at <= fecha_hasta)
        if texto:
            base = base.where(ConsultaHistorialModel.pregunta.ilike(f"%{texto}%"))

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self._session.execute(total_stmt)).scalar() or 0)

        stmt = (
            base.order_by(ConsultaHistorialModel.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        rows = (await self._session.execute(stmt)).all()
        items = [
            ConsultaHistorialAdmin(
                id=model.id,
                expediente_id=model.expediente_id,
                usuario_id=model.usuario_id,
                usuario_carnet=carnet,
                usuario_nombre=nombre,
                pregunta=model.pregunta,
                respuesta=model.respuesta,
                tipo_respuesta=model.tipo_respuesta,
                latencia_ms=model.latencia_ms,
                modelo_llm=model.modelo_llm,
                fuentes_recuperadas=model.fuentes_recuperadas,
                created_at=model.created_at,
                estado=model.estado,
            )
            for model, carnet, nombre in rows
        ]
        return items, total

    async def eliminar_soft_admin(self, historial_id: int) -> bool:
        """Soft delete de CUALQUIER entrada (solo admin, sin propietario)."""
        stmt = select(ConsultaHistorialModel).where(
            ConsultaHistorialModel.id == historial_id,
            ConsultaHistorialModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.activo = False
        await self._session.flush()
        await self._session.commit()
        return True

    async def resumen_dashboard(self) -> DashboardResumen:
        """Agregados para el Dashboard admin (resumen de chats y modelos)."""
        base = select(ConsultaHistorialModel).where(
            ConsultaHistorialModel.activo == True  # noqa: E712
        )

        total = int(
            (
                await self._session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar()
            or 0
        )
        if total == 0:
            return DashboardResumen(
                total_consultas=0,
                en_progreso=0,
                completadas=0,
                con_error=0,
                por_tipo=[],
                por_modelo=[],
                por_usuario=[],
                consultas_por_dia=[],
            )

        # Estados.
        por_estado = {
            (r[0] or "en_progreso"): r[1]
            for r in (
                await self._session.execute(
                    select(ConsultaHistorialModel.estado, func.count())
                    .where(ConsultaHistorialModel.activo == True)  # noqa: E712
                    .group_by(ConsultaHistorialModel.estado)
                )
            ).all()
        }

        # Por tipo de respuesta.
        tipos = (
            await self._session.execute(
                select(ConsultaHistorialModel.tipo_respuesta, func.count())
                .where(
                    ConsultaHistorialModel.tipo_respuesta.is_not(None),
                    ConsultaHistorialModel.activo == True,  # noqa: E712
                )
                .group_by(ConsultaHistorialModel.tipo_respuesta)
                .order_by(func.count().desc())
                .limit(12)
            )
        ).all()
        por_tipo = [ResumenTipo(tipo_respuesta=t or "sin_clasificar", cantidad=c) for t, c in tipos]

        # Por modelo LLM (uso + latencia media).
        modelos = (
            await self._session.execute(
                select(
                    ConsultaHistorialModel.modelo_llm,
                    func.count(),
                    func.avg(ConsultaHistorialModel.latencia_ms),
                )
                .where(
                    ConsultaHistorialModel.modelo_llm.is_not(None),
                    ConsultaHistorialModel.estado == "completado",
                    ConsultaHistorialModel.activo == True,  # noqa: E712
                )
                .group_by(ConsultaHistorialModel.modelo_llm)
                .order_by(func.count().desc())
            )
        ).all()
        por_modelo = [
            ResumenModelo(
                modelo_llm=m,
                cantidad=c,
                latencia_promedio_ms=round(avg) if avg is not None else None,
            )
            for m, c, avg in modelos
        ]

        # Por usuario.
        usuarios = (
            await self._session.execute(
                select(
                    ConsultaHistorialModel.usuario_id,
                    UsuarioModel.carnet,
                    UsuarioModel.nombre,
                    func.count(),
                )
                .join(UsuarioModel, UsuarioModel.id == ConsultaHistorialModel.usuario_id)
                .where(ConsultaHistorialModel.activo == True)  # noqa: E712
                .group_by(
                    ConsultaHistorialModel.usuario_id,
                    UsuarioModel.carnet,
                    UsuarioModel.nombre,
                )
                .order_by(func.count().desc())
                .limit(12)
            )
        ).all()
        por_usuario = [
            ResumenUsuario(
                usuario_id=uid,
                usuario_carnet=carnet,
                usuario_nombre=nombre,
                cantidad=c,
            )
            for uid, carnet, nombre, c in usuarios
        ]

        # Por dia (ultimos 14 dias).
        desde = datetime.now(UTC) - timedelta(days=13)
        dias = (
            await self._session.execute(
                select(func.date(ConsultaHistorialModel.created_at), func.count())
                .where(
                    ConsultaHistorialModel.created_at >= desde,
                    ConsultaHistorialModel.activo == True,  # noqa: E712
                )
                .group_by(func.date(ConsultaHistorialModel.created_at))
                .order_by(func.date(ConsultaHistorialModel.created_at))
            )
        ).all()
        consultas_por_dia = [ResumenDia(fecha=d.isoformat(), cantidad=c) for d, c in dias]

        return DashboardResumen(
            total_consultas=total,
            en_progreso=int(por_estado.get("en_progreso", 0)),
            completadas=int(por_estado.get("completado", 0)),
            con_error=int(por_estado.get("error", 0)),
            por_tipo=por_tipo,
            por_modelo=por_modelo,
            por_usuario=por_usuario,
            consultas_por_dia=consultas_por_dia,
        )

    def _to_domain(self, model: ConsultaHistorialModel) -> ConsultaHistorial:
        return ConsultaHistorial(
            id=model.id,
            expediente_id=model.expediente_id,
            usuario_id=model.usuario_id,
            pregunta=model.pregunta,
            respuesta=model.respuesta,
            tipo_respuesta=model.tipo_respuesta,
            fuentes_recuperadas=model.fuentes_recuperadas,
            latencia_ms=model.latencia_ms,
            modelo_llm=model.modelo_llm,
            estado=model.estado,
            activo=model.activo,
            created_at=model.created_at,
        )


def get_consulta_historial_repo(
    session: AsyncSession,
) -> ConsultaHistorialRepo:
    """Factory para inyeccion de dependencias."""
    return ConsultaHistorialRepoImpl(session)
