"""Repositorio PostgreSQL: FragmentoRepo.

Implementa el puerto application.ports.FragmentoRepo usando SQLAlchemy async.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.fragmento import FragmentoModel
from src.adapters.postgres.models.norma import NormaModel
from src.adapters.postgres.models.obra import ObraModel
from src.application.ports.fragmento_repo import FragmentoRepo


class FragmentoRepoImpl(FragmentoRepo):
    """Implementación concreta de FragmentoRepo para PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, fragmento: Any) -> Any:
        """Inserta un Fragmento. Devuelve la entidad con ID y qdrant_point_id."""
        model = FragmentoModel(
            norma_id=fragmento.norma_id,
            obra_id=fragmento.obra_id,
            expediente_id=fragmento.expediente_id,
            qdrant_point_id=fragmento.qdrant_point_id,
            texto=fragmento.texto,
            padre_ref_id=fragmento.padre_ref_id,
            padre_ref_key=fragmento.padre_ref_key,
            nivel_jerarquico=fragmento.nivel_jerarquico,
            metadatos=fragmento.metadatos,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)

        fragmento.id = model.id
        return fragmento

    async def save_many(self, fragmentos: list[Any]) -> list[Any]:
        """Inserta lote de Fragmentos (batch)."""
        models = [
            FragmentoModel(
                norma_id=f.norma_id,
                obra_id=f.obra_id,
                expediente_id=f.expediente_id,
                qdrant_point_id=f.qdrant_point_id,
                texto=f.texto,
                padre_ref_id=f.padre_ref_id,
                padre_ref_key=f.padre_ref_key,
                nivel_jerarquico=f.nivel_jerarquico,
                metadatos=f.metadatos,
            )
            for f in fragmentos
        ]
        self._session.add_all(models)
        await self._session.flush()
        for f, m in zip(fragmentos, models, strict=True):
            f.id = m.id
        await self._session.commit()
        return fragmentos

    async def asignar_padres_por_ids(self, pares: list[tuple[int, int]]) -> None:
        """UPDATE batch padre_ref_id por (id_hijo, id_padre) (D-S5K-01)."""
        if not pares:
            return

        # UPDATE textual por (hijo, padre): evita el ORM bulk (exige PK
        # por fila y choca con los objetos recién insertados por save_many
        # en la misma sesión). Pares típicos <100; un executemany basta.
        from sqlalchemy import text

        await self._session.execute(
            text("UPDATE fragmento SET padre_ref_id = :padre WHERE id = :hijo"),
            [{"hijo": hijo, "padre": padre} for hijo, padre in pares],
        )
        await self._session.commit()

    async def get_by_norma(self, norma_id: int) -> list[Any]:
        """Obtiene todos los Fragmentos de una Norma."""
        stmt = select(FragmentoModel).where(FragmentoModel.norma_id == norma_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def get_articulos(self, pares: list[tuple[str, int]]) -> list[Any]:
        """Artículos citados (p. ej. por el criterio del vocal), de normas globales activas.

        Por artículo, el fragmento entero (sin `numeral`) si existe; si no, sus numerales.
        """
        if not pares:
            return []
        from sqlalchemy import and_

        articulo = FragmentoModel.metadatos["numero_articulo"].astext
        stmt = (
            select(FragmentoModel, NormaModel.abreviatura)
            .join(NormaModel, NormaModel.id == FragmentoModel.norma_id)
            .where(
                NormaModel.activo.is_(True),
                NormaModel.estado_visibilidad == "global",
                or_(*(and_(NormaModel.abreviatura == ab, articulo == str(n)) for ab, n in pares)),
            )
            .order_by(FragmentoModel.id)
        )
        por_articulo: dict[tuple[str, str], list[Any]] = {}
        for model, abreviatura in (await self._session.execute(stmt)).all():
            # numero_articulo es número en el JSONB: se normaliza a texto para la clave.
            clave = (abreviatura, str(model.metadatos["numero_articulo"]))
            por_articulo.setdefault(clave, []).append(model)
        resultado = []
        for ab, n in pares:
            modelos = por_articulo.get((ab, str(n)), [])
            enteros = [m for m in modelos if not (m.metadatos or {}).get("numeral")]
            resultado.extend(self._to_domain(m) for m in (enteros or modelos))
        return resultado

    async def delete_by_obra(self, obra_id: int) -> int:
        """Elimina los fragmentos persistidos de una obra."""
        from sqlalchemy import delete

        result = await self._session.execute(
            delete(FragmentoModel).where(FragmentoModel.obra_id == obra_id)
        )
        await self._session.commit()
        return int(result.rowcount or 0)

    async def get_by_qdrant_ids(self, qdrant_ids: list[str]) -> list[Any]:
        """Obtiene Fragmentos por lista de qdrant_point_id (búsqueda híbrida).

        Excluye fragmentos de normas u obras con soft delete (activo=false):
        eliminar una norma del corpus no debe seguir recuperándola.
        """
        if not qdrant_ids:
            return []
        stmt = (
            select(FragmentoModel)
            .outerjoin(NormaModel, NormaModel.id == FragmentoModel.norma_id)
            .outerjoin(ObraModel, ObraModel.id == FragmentoModel.obra_id)
            .where(
                FragmentoModel.qdrant_point_id.in_(qdrant_ids),
                or_(NormaModel.id.is_(None), NormaModel.activo.is_(True)),
                or_(ObraModel.id.is_(None), ObraModel.activo.is_(True)),
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete_by_norma(self, norma_id: int) -> int:
        """Borra todos los Fragmentos de una Norma. Devuelve count."""
        from sqlalchemy import delete

        stmt = delete(FragmentoModel).where(FragmentoModel.norma_id == norma_id)
        result = await self._session.execute(stmt)
        return result.rowcount

    async def count_by_norma(self, norma_id: int) -> int:
        """Cuenta los Fragmentos de una Norma sin hidratarlos."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(FragmentoModel)
            .where(FragmentoModel.norma_id == norma_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_all_qdrant_ids(self) -> list[str]:
        """Devuelve todos los qdrant_point_id en PG (sin hidratar entidades)."""
        stmt = select(FragmentoModel.qdrant_point_id)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_ascendencia(
        self,
        fragmento_ids: list[int],
        max_depth: int,
    ) -> list[Any]:
        """Obtiene ancestros jerarquicos via CTE recursivo (Regla 6: PG, no Qdrant).

        Recorre padre_ref_id FK self-ref. Excluye las hojas originales.
        """
        if not fragmento_ids:
            return []

        sql = text("""
            WITH RECURSIVE ascendencia AS (
                SELECT id, padre_ref_id, 1 AS depth
                FROM fragmento
                WHERE id = ANY(:ids)

                UNION ALL

                SELECT f.id, f.padre_ref_id, a.depth + 1
                FROM fragmento f
                JOIN ascendencia a ON f.id = a.padre_ref_id
                WHERE a.depth < :max_depth
            )
            SELECT DISTINCT f.*
            FROM fragmento f
            JOIN ascendencia a ON f.id = a.id
            WHERE f.id != ALL(:ids)
        """)

        result = await self._session.execute(sql, {"ids": fragmento_ids, "max_depth": max_depth})
        rows = result.fetchall()
        return [self._to_domain_from_row(row) for row in rows]

    async def list_fragmentos(
        self,
        pagina: int = 1,
        por_pagina: int = 10,
        norma_id: int | None = None,
        tipo_chunk: str | None = None,
        nivel_jerarquico: int | None = None,
        texto: str | None = None,
    ) -> Any:
        """Devuelve una pagina de fragmentos con total, aplicando filtros."""
        from sqlalchemy import func

        from src.application.ports.fragmento_repo import PaginaFragmentos

        conditions = []
        if norma_id is not None:
            conditions.append(FragmentoModel.norma_id == norma_id)
        if nivel_jerarquico is not None:
            conditions.append(FragmentoModel.nivel_jerarquico == nivel_jerarquico)
        if tipo_chunk is not None:
            # tipo_chunk vive dentro del JSONB metadatos.
            conditions.append(FragmentoModel.metadatos["tipo_chunk"].astext == tipo_chunk)
        if texto:
            conditions.append(FragmentoModel.texto.ilike(f"%{texto}%"))

        base = select(FragmentoModel).where(*conditions)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar()
            or 0
        )
        stmt = (
            base.order_by(FragmentoModel.norma_id, FragmentoModel.id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
        result = await self._session.execute(stmt)
        return PaginaFragmentos(
            items=[self._to_domain(m) for m in result.scalars().all()],
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
        )

    async def listar_vocabulario(self) -> frozenset[str]:
        """Tokens unicos del corpus (Capa A) — cacheado por proceso.

        Implementacion via src.adapters.postgres.vocabulario para compartir
        la cache global y su invalidation al reindexar.
        """
        from src.adapters.postgres.vocabulario import get_vocabulario

        return await get_vocabulario(self._session)

    async def get_by_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        limit: int = 20,
    ) -> list[Any]:
        """Fragmentos de obrados de un expediente visibles para el usuario (fallback).

        Antecedentes de borrador deben venir de obrados aunque el vector search
        los filtre por score bajo (OCR ruidoso). Hace JOIN con obra para
        aplicar Regla 5: publicado/global o propietario_id == usuario_id.
        """
        from sqlalchemy import or_

        from src.adapters.postgres.models.obra import ObraModel

        stmt = (
            select(FragmentoModel)
            .join(ObraModel, FragmentoModel.obra_id == ObraModel.id)
            .where(
                FragmentoModel.expediente_id == expediente_id,
                FragmentoModel.obra_id.is_not(None),
                or_(
                    ObraModel.estado_visibilidad.in_(["publicado", "global"]),
                    ObraModel.propietario_id == usuario_id,
                ),
            )
            .order_by(FragmentoModel.nivel_jerarquico, FragmentoModel.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: FragmentoModel) -> Any:
        """Convierte modelo ORM -> entidad de dominio."""
        from src.domain.entities.fragmento import Fragmento

        return Fragmento(
            id=model.id,
            norma_id=model.norma_id,
            obra_id=model.obra_id,
            expediente_id=model.expediente_id,
            qdrant_point_id=model.qdrant_point_id,
            texto=model.texto,
            padre_ref_id=model.padre_ref_id,
            padre_ref_key=model.padre_ref_key,
            nivel_jerarquico=model.nivel_jerarquico,
            metadatos=model.metadatos,
            tipo_chunk=model.metadatos.get("tipo_chunk") if model.metadatos else None,
        )

    def _to_domain_from_row(self, row: Any) -> Any:
        """Convierte row de CTE (sqlalchemy.Row) -> entidad de dominio.

        Los campos vienen en el orden del SELECT f.*: id, norma_id, obra_id,
        expediente_id, qdrant_point_id, texto, padre_ref_id, padre_ref_key,
        nivel_jerarquico, metadatos.
        """
        from src.domain.entities.fragmento import Fragmento

        return Fragmento(
            id=row.id,
            norma_id=row.norma_id,
            obra_id=row.obra_id,
            expediente_id=row.expediente_id,
            qdrant_point_id=row.qdrant_point_id,
            texto=row.texto,
            padre_ref_id=row.padre_ref_id,
            padre_ref_key=row.padre_ref_key,
            nivel_jerarquico=row.nivel_jerarquico,
            metadatos=row.metadatos,
            tipo_chunk=row.metadatos.get("tipo_chunk") if row.metadatos else None,
        )


def get_fragmento_repo(session: AsyncSession) -> FragmentoRepo:
    """Factory para inyección de dependencias."""
    return FragmentoRepoImpl(session)
