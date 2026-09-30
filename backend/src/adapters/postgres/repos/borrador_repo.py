"""Repositorio PostgreSQL: BorradorRepoImpl.

Implementa el puerto application.ports.borrador_repo.BorradorRepo.
Mapea la entidad de dominio Borrador ↔ modelo ORM BorradorModel.

Regla 7 Trail of Bits (BLOQUEANTE): el filtro de propiedad
`propietario_id == usuario_id` vive AQUÍ en el adapter. El use case siempre
pasa `usuario_id`; este repo lo aplica SIEMPRE. No es un parámetro
opcional del caller.

Detalles de implementación:
- `actualizar_estado` filtra por propietario_id antes del UPDATE — si el
  caller no es el dueño, devuelve None (403 en router, no diferenciado de
  'no existe' para evitar information leak por timing/oracle).
- `actualizar_contenido` NO filtra por propietario — lo invoca el flujo
  interno de GenerarBorrador (cuando el stream LLM termina), no un usuario.
- `listar_por_expediente` filtra por propietario_id = usuario_id (Sprint 6
  sinthood: solo el dueño ve sus borradores en estado 'borrador').
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.borrador import BorradorModel
from src.application.ports.borrador_repo import BorradorRepo
from src.domain.entities.borrador import Borrador
from src.domain.services.validador_propietario import validar_usuario_id


class BorradorRepoImpl(BorradorRepo):
    """Implementación PostgreSQL del repositorio de borradores."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, borrador: Borrador) -> Borrador:
        """Inserta un borrador. Devuelve entidad con id y created_at asignados."""
        model = BorradorModel(
            expediente_id=borrador.expediente_id,
            propietario_id=borrador.propietario_id,
            tipo=borrador.tipo,
            contenido=borrador.contenido,
            plantilla_usada=borrador.plantilla_usada,
            contexto_recuperado=borrador.contexto_recuperado,
            estado=borrador.estado,
            chat_id=borrador.chat_id,
            mensaje_id=borrador.mensaje_id,
            layout=borrador.layout,
            razonamiento=borrador.razonamiento or "",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()

        borrador.id = model.id
        borrador.created_at = model.created_at
        return borrador

    async def obtener_por_id(self, borrador_id: int) -> Borrador | None:
        """Obtiene un borrador por id. Sin filtro de propietario.

        El filtro de propietario lo aplica el use case (Regla 7) comparando
        el campo de la entidad con usuario_id del JWT.
        """
        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        return self._to_domain(model) if model is not None else None

    async def listar_por_expediente(
        self,
        expediente_id: int,
        propietario_id: int,
    ) -> list[Borrador]:
        """Lista borradores de un expediente visibles para el usuario.

        Regla 7: el propietario ve sus borradores (estado 'borrador' o
        'publicado'); los borradores 'publicado' de otros usuarios tambien
        son visibles (auto de vista publicado = publico).
        """
        validar_usuario_id(propietario_id)

        stmt = select(BorradorModel).where(
            BorradorModel.expediente_id == expediente_id,
            BorradorModel.activo == True,  # noqa: E712 — soft delete CRITICAL #3
            or_(
                BorradorModel.propietario_id == propietario_id,
                BorradorModel.estado == "publicado",
            ),
        )
        stmt = stmt.order_by(BorradorModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def listar_por_propietario(self, propietario_id: int) -> list[Borrador]:
        """Lista todos los borradores del propietario (vista 'Mis Borradores')."""
        validar_usuario_id(propietario_id)

        stmt = (
            select(BorradorModel)
            .where(
                BorradorModel.propietario_id == propietario_id,
                BorradorModel.activo == True,  # noqa: E712
            )
            .order_by(BorradorModel.updated_at.desc(), BorradorModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def obtener_por_chat(self, chat_id: int, propietario_id: int) -> Borrador | None:
        """Obtiene el borrador de un chat (propietario). Regla 7."""
        validar_usuario_id(propietario_id)

        stmt = (
            select(BorradorModel)
            .where(
                BorradorModel.chat_id == chat_id,
                BorradorModel.propietario_id == propietario_id,
                BorradorModel.activo == True,  # noqa: E712
            )
            .order_by(BorradorModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model is not None else None

    async def actualizar_estado(
        self,
        borrador_id: int,
        estado: str,
        propietario_id: int,
    ) -> Borrador | None:
        """Cambia estado 'borrador' -> 'publicado' validando propietario.

        Regla 7 (BLOQUEANTE): el filtro `BorradorModel.propietario_id ==
        propietario_id` vive en el adapter. Si no matchea (o el borrador no
        existe), devuelve None. El use case traduce a BorradorNoPropioError.
        """
        validar_usuario_id(propietario_id)

        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.propietario_id == propietario_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        # Idempotente: si ya esta en el estado pedido, no muta updated_at.
        if model.estado == estado:
            return self._to_domain(model)

        model.estado = estado
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_estado_supervisor(
        self,
        borrador_id: int,
        estado: str,
        desde: str,
    ) -> Borrador | None:
        """Cambia el estado de un borrador activo sin validar propietario (supervisor).

        Ciclo obrado -> oficial: aprueba ('pendiente_oficial' -> 'oficial') o
        desoficializa ('oficial' -> 'pendiente_oficial' | 'publicado' | 'borrador').
        Solo transiciona si el estado actual es `desde`; si no (o si esta inactivo)
        devuelve None y no cambia nada. NO es el propietario del borrador del
        operador, por eso no se filtra. El guard de rol vive en el router.
        """
        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.estado == desde,
            BorradorModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.estado = estado
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_contenido_supervisor(
        self,
        borrador_id: int,
        contenido: str,
        layout: list[dict] | None = None,
    ) -> Borrador | None:
        """Supervisor corrige un borrador en revision ('pendiente_oficial') ajeno.

        Solo aplica a ese estado (activo): un oficial no se edita, se desoficializa
        antes. El guard de rol vive en el router, igual que `actualizar_estado_supervisor`.
        """
        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.estado == "pendiente_oficial",
            BorradorModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.contenido = contenido
        if layout is not None:
            model.layout = layout
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_contenido(
        self,
        borrador_id: int,
        contenido: str,
    ) -> Borrador | None:
        """Actualiza el contenido de un borrador. Sin filtro de propietario.

        Invocado por GenerarBorrador (Fase 3.1) cuando el stream LLM
        termina. NO es un endpoint de usuario final.
        """
        stmt = select(BorradorModel).where(BorradorModel.id == borrador_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.contenido = contenido
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def actualizar_contenido_con_fuentes(
        self,
        borrador_id: int,
        contenido: str,
        fuentes: dict | None,
        razonamiento: str = "",
    ) -> Borrador | None:
        """Actualiza contenido + contexto_recuperado de un borrador.

        Invocado por GuardarBorrador al pulsar 'Actualizar mi borrador'
        (borrador ya propiedad-verificado via obtener_por_chat).
        """
        stmt = select(BorradorModel).where(BorradorModel.id == borrador_id)
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.contenido = contenido
        model.contexto_recuperado = fuentes
        model.razonamiento = razonamiento or ""
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def eliminar_soft(
        self,
        borrador_id: int,
        propietario_id: int,
    ) -> bool:
        """Soft delete: activo=False SOLO si el borrador es del propietario.

        Regla 7 (BLOQUEANTE): el filtro `propietario_id == propietario_id`
        vive en el adapter. True si se elimino; False si no existe o es ajeno.
        """
        validar_usuario_id(propietario_id)

        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.propietario_id == propietario_id,
            BorradorModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return False

        model.activo = False
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        return True

    async def actualizar_contenido_propietario(
        self,
        borrador_id: int,
        propietario_id: int,
        contenido: str,
        layout: list[dict] | None = None,
    ) -> Borrador | None:
        """Actualiza contenido (+ layout fiel opcional) de un borrador, Regla 7.

        Si layout es None no se toca la columna (compat: edicion solo texto).
        Si se provee (lista vacia o con bloques) se persiste y se regenera el
        .md desde esos bloques en el caller; guardar todo actualiza ambos.
        """
        validar_usuario_id(propietario_id)

        stmt = select(BorradorModel).where(
            BorradorModel.id == borrador_id,
            BorradorModel.propietario_id == propietario_id,
            BorradorModel.estado == "borrador",
            BorradorModel.activo == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        model = result.scalars().one_or_none()
        if model is None:
            return None

        model.contenido = contenido
        if layout is not None:
            model.layout = layout
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_domain(model)

    def _to_domain(self, model: BorradorModel) -> Borrador:
        return Borrador(
            id=model.id,
            expediente_id=model.expediente_id,
            propietario_id=model.propietario_id,
            tipo=model.tipo,
            contenido=model.contenido,
            plantilla_usada=model.plantilla_usada,
            contexto_recuperado=model.contexto_recuperado,
            estado=model.estado,
            activo=model.activo,
            chat_id=model.chat_id,
            mensaje_id=model.mensaje_id,
            layout=model.layout,
            razonamiento=model.razonamiento or "",
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def get_borrador_repo(session: AsyncSession) -> BorradorRepo:
    """Factory para inyección de dependencias."""
    return BorradorRepoImpl(session)
