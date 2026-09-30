"""Adapter: SqlAuthRepository — Repositorio de auth para PostgreSQL.

Implementa AuthRepository (Protocol) usando SQLAlchemy async + ORM models.
Mapea entidades de dominio <-> ORM. Almacena SHA-256(token) en refresh_token
(nunca el raw). Las cuentas de intentos se hacen con COUNT(*) filtrado por
ventana temporal.

Sprint 1 Auth (plan v3, F1.4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.intentos_login import IntentosLoginModel
from src.adapters.postgres.models.refresh_token import RefreshTokenModel
from src.adapters.postgres.models.usuario import UsuarioModel
from src.application.auth import crear_usuario as crear_usuario_uc
from src.application.ports.auth_repository import AuthRepository, RefreshTokenData
from src.domain.entities.usuario import RolUsuario, Usuario


class SqlAuthRepository:
    """Implementacion concreta de AuthRepository para PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_carnet(self, carnet: str) -> Usuario | None:
        stmt = select(UsuarioModel).where(UsuarioModel.carnet == carnet)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def get_by_id(self, usuario_id: int) -> Usuario | None:
        stmt = select(UsuarioModel).where(UsuarioModel.id == usuario_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def crear_usuario(self, usuario: Usuario) -> Usuario:
        model = UsuarioModel(
            nombre=usuario.nombre,
            carnet=usuario.carnet,
            password_hash=usuario.password_hash,
            rol=usuario.rol,
            cargo=usuario.cargo,
            activo=usuario.activo,
            email=usuario.email,
            email_verificado=usuario.email_verificado,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # Carnet duplicado (unique ix_usuario_carnet). Rollback para que la
            # sesion no quede en estado transaccional invalido.
            await self._session.rollback()
            raise crear_usuario_uc.CarnetDuplicadoError from exc
        await self._session.refresh(model)
        await self._session.commit()
        usuario.id = model.id
        usuario.created_at = model.created_at
        return usuario

    async def actualizar_usuario(
        self, usuario: Usuario, carnet_original: str | None = None
    ) -> Usuario:
        identificador = carnet_original or usuario.carnet
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == identificador)
            .values(
                carnet=usuario.carnet,
                nombre=usuario.nombre,
                rol=usuario.rol,
                cargo=usuario.cargo,
                activo=usuario.activo,
                password_hash=usuario.password_hash,
                email=usuario.email,
                email_verificado=usuario.email_verificado,
                codigo_2fa_hash=usuario.codigo_2fa_hash,
                codigo_2fa_expira=usuario.codigo_2fa_expira,
                intentos_codigo=usuario.intentos_codigo,
                bloqueado_hasta=usuario.bloqueado_hasta,
            )
            .returning(UsuarioModel.id)
        )
        try:
            result = await self._session.execute(stmt)
            usuario.id = result.scalar_one()
            await self._session.commit()
        except IntegrityError as exc:
            # Carnet nuevo duplicado (unique ix_usuario_carnet).
            await self._session.rollback()
            raise crear_usuario_uc.CarnetDuplicadoError from exc
        return usuario

    async def listar_usuarios(self) -> list[Usuario]:
        stmt = select(UsuarioModel).order_by(UsuarioModel.carnet.asc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def guardar_refresh_token(
        self, usuario_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        model = RefreshTokenModel(
            id=uuid4().hex,
            usuario_id=usuario_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revocado=False,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()

    async def revocar_refresh_token(self, token_hash: str) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .values(revocado=True)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def revocar_todos_refresh_tokens(self, usuario_id: int) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.usuario_id == usuario_id,
                RefreshTokenModel.revocado.is_(False),
            )
            .values(revocado=True)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_refresh_token(self, token_hash: str) -> RefreshTokenData | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return RefreshTokenData(
            id=model.id,
            usuario_id=model.usuario_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            revocado=model.revocado,
            created_at=model.created_at,
        )

    async def registrar_intento(self, carnet: str, ip: str, exitoso: bool) -> None:
        model = IntentosLoginModel(carnet=carnet, ip=ip, exitoso=exitoso)
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()

    async def contar_intentos_fallidos(self, carnet: str, desde: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(IntentosLoginModel)
            .where(
                IntentosLoginModel.carnet == carnet,
                IntentosLoginModel.exitoso.is_(False),
                IntentosLoginModel.timestamp >= desde,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def contar_intentos_por_ip(self, ip: str, desde: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(IntentosLoginModel)
            .where(
                IntentosLoginModel.ip == ip,
                IntentosLoginModel.timestamp >= desde,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def actualizar_email(self, carnet: str, email: str) -> None:
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == carnet)
            .values(email=email, email_verificado=False)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def marcar_email_verificado(self, carnet: str) -> None:
        stmt = (
            update(UsuarioModel).where(UsuarioModel.carnet == carnet).values(email_verificado=True)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def guardar_codigo_2fa(self, carnet: str, codigo_hash: str, expira: datetime) -> None:
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == carnet)
            .values(
                codigo_2fa_hash=codigo_hash,
                codigo_2fa_expira=expira,
                intentos_codigo=0,
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def verificar_codigo_2fa(self, carnet: str, codigo_hash: str) -> bool:
        stmt = select(UsuarioModel).where(UsuarioModel.carnet == carnet)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None or model.codigo_2fa_hash != codigo_hash:
            return False
        return model.codigo_2fa_expira is not None and model.codigo_2fa_expira > datetime.now(UTC)

    async def incrementar_intentos_2fa(self, carnet: str) -> int:
        # Una sola sentencia atomica: leer y escribir `+1` pierde incrementos ante
        # verificaciones concurrentes y eludiria el bloqueo a los 3 intentos.
        intentos = func.coalesce(UsuarioModel.intentos_codigo, 0) + 1
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == carnet)
            .values(
                intentos_codigo=intentos,
                bloqueado_hasta=case(
                    (intentos >= 3, datetime.now(UTC) + timedelta(hours=1)),
                    else_=UsuarioModel.bloqueado_hasta,
                ),
            )
            .returning(UsuarioModel.intentos_codigo)
        )
        result = await self._session.execute(stmt)
        nuevos = result.scalar_one_or_none()
        await self._session.commit()
        return int(nuevos) if nuevos is not None else 0

    async def limpiar_codigo_2fa(self, carnet: str) -> None:
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == carnet)
            .values(codigo_2fa_hash=None, codigo_2fa_expira=None, intentos_codigo=0)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def desbloquear_2fa(self, carnet: str) -> None:
        stmt = (
            update(UsuarioModel)
            .where(UsuarioModel.carnet == carnet)
            .values(bloqueado_hasta=None, intentos_codigo=0)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    def _to_domain(self, model: UsuarioModel) -> Usuario:
        return Usuario(
            id=model.id,
            nombre=model.nombre,
            carnet=model.carnet,
            password_hash=model.password_hash,
            rol=cast(RolUsuario, model.rol),
            cargo=model.cargo,
            activo=model.activo,
            created_at=model.created_at,
            email=model.email,
            email_verificado=model.email_verificado,
            codigo_2fa_hash=model.codigo_2fa_hash,
            codigo_2fa_expira=model.codigo_2fa_expira,
            intentos_codigo=model.intentos_codigo,
            bloqueado_hasta=model.bloqueado_hasta,
        )


def get_auth_repo(session: AsyncSession) -> AuthRepository:
    """Factory para inyeccion de dependencias."""
    return SqlAuthRepository(session)
