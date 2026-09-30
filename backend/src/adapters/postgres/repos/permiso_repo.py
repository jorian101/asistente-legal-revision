"""Adapter: SqlPermisoRepo — Repositorio de módulos y permisos para PostgreSQL.

Implementa PermisoRepo (Protocol) usando SQLAlchemy async + ORM models.
Mapea entidades de dominio <-> ORM. El catálogo de módulos se siembra por
migración Alembic; este repo solo lo lee y actualiza metadata. Los overrides
de permisos viven en `usuario_modulo_permiso` (NULL = seguir default del rol).

Decision `plan/permisos-crud-modulos`: el default por rol está en código
(domain/entities/permiso.py), esta tabla guarda SOLO overrides por usuario.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.modulo import ModuloModel
from src.adapters.postgres.models.usuario_modulo_permiso import UsuarioModuloPermisoModel
from src.application.ports.permiso_repo import PermisoRepo
from src.domain.entities.permiso import Modulo, PermisoCRUD


class SqlPermisoRepo:
    """Implementacion concreta de PermisoRepo para PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def listar_modulos(self) -> list[Modulo]:
        stmt = select(ModuloModel).order_by(ModuloModel.orden.asc())
        result = await self._session.execute(stmt)
        return [self._modulo_to_domain(m) for m in result.scalars().all()]

    async def actualizar_modulo(self, clave: str, **campos) -> Modulo:
        permitidos = {"nombre", "descripcion", "ruta", "orden", "activo"}
        values = {k: v for k, v in campos.items() if k in permitidos}
        if not values:
            raise ValueError("Sin campos validos para actualizar el modulo.")
        stmt = (
            update(ModuloModel)
            .where(ModuloModel.clave == clave)
            .values(**values)
            .returning(ModuloModel)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise KeyError(clave)
        await self._session.commit()
        return self._modulo_to_domain(model)

    async def get_permisos_usuario(self, usuario_id: int) -> dict[str, PermisoCRUD]:
        stmt = (
            select(ModuloModel.clave, UsuarioModuloPermisoModel)
            .join(UsuarioModuloPermisoModel, UsuarioModuloPermisoModel.modulo_id == ModuloModel.id)
            .where(UsuarioModuloPermisoModel.usuario_id == usuario_id)
        )
        result = await self._session.execute(stmt)
        return {
            clave: PermisoCRUD(
                puede_crear=row.puede_crear,
                puede_leer=row.puede_leer,
                puede_actualizar=row.puede_actualizar,
                puede_eliminar=row.puede_eliminar,
            )
            for clave, row in result.all()
        }

    async def reemplazar_permisos_usuario(
        self, usuario_id: int, permisos: dict[str, PermisoCRUD]
    ) -> None:
        # Resolver modulo_id por clave.
        stmt = select(ModuloModel.clave, ModuloModel.id).where(
            ModuloModel.clave.in_(permisos.keys())
        )
        result = await self._session.execute(stmt)
        clave_a_id = dict(result.all())
        desconocidas = set(permisos.keys()) - set(clave_a_id.keys())
        if desconocidas:
            raise KeyError(", ".join(sorted(desconocidas)))

        # Borrar overrides que dejaron de existir o que quedaron vacios (todos None).
        stmt_del = delete(UsuarioModuloPermisoModel).where(
            UsuarioModuloPermisoModel.usuario_id == usuario_id
        )
        await self._session.execute(stmt_del)

        for clave, p in permisos.items():
            es_vacio = (
                p.puede_crear is None
                and p.puede_leer is None
                and p.puede_actualizar is None
                and p.puede_eliminar is None
            )
            if es_vacio:
                continue  # sin override: seguir default del rol
            model = UsuarioModuloPermisoModel(
                usuario_id=usuario_id,
                modulo_id=clave_a_id[clave],
                puede_crear=p.puede_crear,
                puede_leer=p.puede_leer,
                puede_actualizar=p.puede_actualizar,
                puede_eliminar=p.puede_eliminar,
            )
            self._session.add(model)

        await self._session.flush()
        await self._session.commit()

    @staticmethod
    def _modulo_to_domain(model: ModuloModel) -> Modulo:
        return Modulo(
            id=model.id,
            clave=model.clave,
            nombre=model.nombre,
            descripcion=model.descripcion,
            ruta=model.ruta,
            orden=model.orden,
            activo=model.activo,
        )


def get_permiso_repo(session: AsyncSession) -> PermisoRepo:
    """Factory para inyeccion de dependencias."""
    return SqlPermisoRepo(session)
