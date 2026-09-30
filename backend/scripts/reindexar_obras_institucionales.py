"""CLI: reindexar_obras_institucionales.py — Reindexa obras.

Fix Fase 1, opcion B: las obras de expediente cargadas institucionalmente deben ser
publicadas y con autor_instancia = tribunal_origen, visibles para todos (Regla 5).
Qdrant tenia propietario_id=4 fantasma (data-drift) y visibilidad privada;
PG ya tiene propietario 26 pero Qdrant desactualizado.

Uso:
    uv run python scripts/reindexar_obras_institucionales.py [--dry-run] [--yes]

Requiere stack (PG + Qdrant + Ollama). Re-embebe cada obra afectada.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.http.dependencies import build_embedder
from src.adapters.postgres.models.expediente import ExpedienteModel
from src.adapters.postgres.models.obra import ObraModel
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.obra_repo import ObraRepoImpl
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.application.expedientes.indexar_obra import IndexarObra
from src.config import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description="Reindexa obras institucionales")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra, no modifica")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmacion")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Cargar mapa expediente_id -> tribunal_origen
            exp_rows = await session.execute(
                select(ExpedienteModel.id, ExpedienteModel.tribunal_origen)
            )
            tribunal_por_exp = {r[0]: r[1] for r in exp_rows.fetchall()}

            # Obras institucionales: con expediente, autor null o privado
            # Incluimos todas con expediente para completar autor.
            obras_stmt = (
                select(ObraModel)
                .where(
                    ObraModel.expediente_id.isnot(None),
                    ObraModel.fuente == "carga_usuario",
                )
                .order_by(ObraModel.id)
            )
            result = await session.execute(obras_stmt)
            obras = result.scalars().all()

            afectadas = []
            for obra in obras:
                tribunal = tribunal_por_exp.get(obra.expediente_id)
                necesita_autor = obra.autor_instancia is None and tribunal is not None
                # Solo obras procesales (no doctrina/criterio) deben pasar a publicado
                necesita_visibilidad = (
                    obra.estado_visibilidad == "privado"
                    and obra.tipo_documento not in ("doctrina", "criterio")
                )
                if necesita_autor or necesita_visibilidad:
                    afectadas.append(obra)

            print(f"Total obras institucionales: {len(obras)}")
            print(f"Afectadas (autor null o privado): {len(afectadas)}")
            for obra in afectadas:
                tribunal = tribunal_por_exp.get(obra.expediente_id)
                print(
                    f"  obra id={obra.id} exp={obra.expediente_id} tipo={obra.tipo_documento} vis={obra.estado_visibilidad} autor_instancia={obra.autor_instancia!r} -> tribunal={tribunal!r}"  # noqa: E501
                )

            if not afectadas:
                print("Nada que corregir.")
                return 0

            if args.dry_run:
                print("(dry-run) No se modifica ni reindexa.")
                return 0

            if not args.yes:
                r = input(f"Corregir PG + reindexar {len(afectadas)} obras en Qdrant? [y/N] ")
                if r.strip().lower() != "y":
                    print("Cancelado.")
                    return 0

            # Corregir PG
            for obra in afectadas:
                tribunal = tribunal_por_exp.get(obra.expediente_id)
                if obra.autor_instancia is None and tribunal:
                    obra.autor_instancia = tribunal
                if obra.estado_visibilidad == "privado":
                    obra.estado_visibilidad = "publicado"
                # marcar pendiente para reindex
                obra.estado_procesamiento = "pendiente"
            await session.commit()
            print("✓ PG corregido (autor_instancia + visibilidad)")

            # Reindexar cada obra afectada
            obra_repo = ObraRepoImpl(session)
            fragmento_repo = FragmentoRepoImpl(session)
            vector_repo = QdrantCorpusRepo()
            embedder = build_embedder(None)
            indexador = IndexarObra(
                obra_repo=obra_repo,
                fragmento_repo=fragmento_repo,
                embedder=embedder,
                vector_repo=vector_repo,
            )

            for obra_model in afectadas:
                # Recargar como dominio (obra_repo.guardar ya hizo flush, pero necesitamos entidad)
                # Construir Obra dominio desde modelo PG corregido
                from src.domain.entities.obra import Obra

                obra_dom = Obra(
                    id=obra_model.id,
                    expediente_id=obra_model.expediente_id,
                    propietario_id=obra_model.propietario_id,
                    tipo_documento=obra_model.tipo_documento,
                    nombre_archivo=obra_model.nombre_archivo,
                    contenido_texto=obra_model.contenido_texto,
                    ruta_archivo=obra_model.ruta_archivo,
                    fojas_inicio=obra_model.fojas_inicio,
                    fojas_fin=obra_model.fojas_fin,
                    estado_visibilidad=obra_model.estado_visibilidad,
                    fuente=obra_model.fuente,
                    tamano_archivo=obra_model.tamano_archivo,
                    estado_procesamiento=obra_model.estado_procesamiento,
                    autor_instancia=obra_model.autor_instancia,
                    created_at=obra_model.created_at,
                    autor=obra_model.autor,
                    fecha_documento=obra_model.fecha_documento,
                    procedencia=obra_model.procedencia,
                    recomendada=obra_model.recomendada,
                )
                print(
                    f"  Reindexando obra id={obra_dom.id} tipo={obra_dom.tipo_documento} exp={obra_dom.expediente_id} ...",  # noqa: E501
                    end=" ",
                    flush=True,
                )
                resp = await indexador.ejecutar(obra_dom)
                await session.commit()
                print(f"OK {resp.fragmentos_creados} fragments, {resp.vectores_indexados} vectores")

            print("✅ Reindexado completo")

            # Tambien corregir doctrina obra 16 visibilidad global vs publicado si aplica
            # La doctrina del expediente (obra 16) ya es global en PG, Qdrant tenia publicado (reindex la arregla si estaba en afectadas? No, porque estado_visibilidad global no es privado)
            # Forzar reindex de obra 16 si Qdrant tiene mismatch
            from qdrant_client import QdrantClient, models

            c = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
            pts, _ = c.scroll(
                "corpus_juridico",
                limit=5,
                with_payload=True,
                with_vectors=False,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="obra_id", match=models.MatchValue(value=16))]
                ),
            )
            if pts:
                vis_q = pts[0].payload.get("visibilidad")
                # obra 16 en PG es global
                exp_vis = await session.get(ObraModel, 16)
                if exp_vis and exp_vis.estado_visibilidad != vis_q:
                    print(
                        f"  Reindexando doctrina exp obra 16 (vis PG {exp_vis.estado_visibilidad!r} vs Qdrant {vis_q!r})..."
                    )
                    from src.domain.entities.obra import Obra as ObraDom

                    obra_dom16 = ObraDom(
                        id=exp_vis.id,
                        expediente_id=exp_vis.expediente_id,
                        propietario_id=exp_vis.propietario_id,
                        tipo_documento=exp_vis.tipo_documento,
                        nombre_archivo=exp_vis.nombre_archivo,
                        contenido_texto=exp_vis.contenido_texto,
                        ruta_archivo=exp_vis.ruta_archivo,
                        fojas_inicio=exp_vis.fojas_inicio,
                        fojas_fin=exp_vis.fojas_fin,
                        estado_visibilidad=exp_vis.estado_visibilidad,
                        fuente=exp_vis.fuente,
                        tamano_archivo=exp_vis.tamano_archivo,
                        estado_procesamiento="pendiente",
                        autor_instancia=exp_vis.autor_instancia,
                        created_at=exp_vis.created_at,
                        autor=exp_vis.autor,
                        fecha_documento=exp_vis.fecha_documento,
                        procedencia=exp_vis.procedencia,
                        recomendada=exp_vis.recomendada,
                    )
                    exp_vis.estado_procesamiento = "pendiente"
                    await session.commit()
                    resp = await indexador.ejecutar(obra_dom16)
                    await session.commit()
                    print(f"  OK doctrina 16 reindexada {resp.fragmentos_creados} frags")

    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(asyncio.run(main()))
