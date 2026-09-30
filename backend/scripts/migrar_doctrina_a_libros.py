"""CLI: migrar_doctrina_a_libros.py — la doctrina subida como obra pasa a libro del corpus.

Doctrina = libros. Las obras `doctrina`/`material_caso` que suben los usuarios se
convierten en fuentes de la categoria `doctrina` (tabla `norma`, coleccion Qdrant
`doctrina`) con el flujo comun privada -> pendiente -> global:

    obra privado -> libro privado | obra publicado -> libro pendiente | global -> global

La obra se desactiva y se borran sus fragmentos y puntos de `corpus_juridico`. Si
estaba vinculada a un expediente, se crea un puntero privado al libro para ese caso.

Por defecto solo muestra el plan (dry-run). `--aplicar` ejecuta y guarda antes un
respaldo JSON de las obras afectadas.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.migrar_sentencias_a_normas import SENTENCIAS  # noqa: E402

_TIPOS = ("doctrina", "material_caso")
_ESTADO_LIBRO = {"privado": "privado", "publicado": "pendiente", "global": "global"}


@dataclass(frozen=True)
class Accion:
    obra_id: int
    nombre: str
    estado: str
    propietario_id: int
    puntero_expediente_id: int | None


def planificar(obras) -> list[Accion]:
    """Plan puro: qué obras son doctrina de usuario migrable a libro."""
    plan: list[Accion] = []
    for o in obras:
        if (
            o.tipo_documento not in _TIPOS
            or not o.activo
            or o.corpus_ref
            or o.estado_visibilidad not in _ESTADO_LIBRO
            or not (o.contenido_texto or "").strip()
            or o.nombre_archivo in SENTENCIAS  # jurisprudencia: otro script
        ):
            continue
        nombre = Path(o.nombre_archivo).stem.replace("-", " ").replace("_", " ").strip()
        plan.append(
            Accion(
                obra_id=o.id,
                nombre=nombre,
                estado=_ESTADO_LIBRO[o.estado_visibilidad],
                propietario_id=o.propietario_id,
                puntero_expediente_id=o.expediente_id,
            )
        )
    return plan


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="ejecuta (por defecto solo plan)")
    args = ap.parse_args()

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from scripts._aviso import aviso_poblar
    from src.adapters.http.dependencies import (
        build_embedder,
        get_vector_repo,
        get_vector_repo_doctrina,
        get_vector_repo_jurisprudencia,
    )
    from src.adapters.postgres.models.obra import ObraModel
    from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
    from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
    from src.adapters.postgres.repos.obra_repo import ObraRepoImpl
    from src.application.corpus.indexar_norma import IndexarNorma
    from src.application.doctrina.seleccionar_corpus import (
        SeleccionarCorpus,
        SeleccionarCorpusRequest,
    )
    from src.application.fuentes.casos_de_uso import SubirFuente
    from src.config import get_settings

    engine = create_async_engine(get_settings().postgres_url_async)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        obras = (await session.execute(select(ObraModel))).scalars().all()
        plan = planificar(obras)
        if not plan:
            print("Nada que migrar.")
            await engine.dispose()
            return 0
        for a in plan:
            extra = (
                f" + puntero al expediente {a.puntero_expediente_id}"
                if a.puntero_expediente_id
                else ""
            )
            print(f"  obra {a.obra_id}: libro «{a.nombre}» ({a.estado}){extra}")
        if not args.aplicar:
            print("Dry-run: usa --aplicar para ejecutar (guarda respaldo JSON antes).")
            await engine.dispose()
            return 0

        por_id = {o.id: o for o in obras}
        respaldo = Path(f"respaldo-doctrina-{datetime.now(UTC):%Y%m%d-%H%M%S}.json")
        respaldo.write_text(
            json.dumps(
                [
                    {
                        c.name: str(getattr(por_id[a.obra_id], c.name))
                        for c in ObraModel.__table__.columns
                    }
                    for a in plan
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Respaldo: {respaldo}")

        norma_repo = SqlNormaRepo(session)
        fragmento_repo = FragmentoRepoImpl(session)
        obra_repo = ObraRepoImpl(session)
        vector = get_vector_repo()
        embedder = build_embedder(None)
        indexar = IndexarNorma(
            text_extractor=None,  # type: ignore[arg-type]  # se usa texto_directo
            embedder=embedder,
            vector_repo=vector,
            norma_repo=norma_repo,
            fragmento_repo=fragmento_repo,
            vector_repo_jurisprudencia=get_vector_repo_jurisprudencia(),
            vector_repo_doctrina=get_vector_repo_doctrina(),
        )
        subir = SubirFuente(indexar, norma_repo)
        for a in plan:
            obra = por_id[a.obra_id]
            resultado = await subir.ejecutar(
                categoria="doctrina",
                nombre=a.nombre,
                ruta=obra.nombre_archivo,
                usuario_id=a.propietario_id,
                es_supervisor=False,
                texto=obra.contenido_texto,
            )
            norma = await norma_repo.get_by_id(resultado.norma_id)
            if a.estado != "privado":
                await norma_repo.actualizar_visibilidad(norma.id, a.estado)
                await get_vector_repo_doctrina().actualizar_payload_norma(
                    norma.id, {"visibilidad": a.estado}
                )
            await vector.delete_by_obra(a.obra_id)
            await fragmento_repo.delete_by_obra(a.obra_id)
            await session.execute(
                update(ObraModel).where(ObraModel.id == a.obra_id).values(activo=False)
            )
            await session.commit()
            if a.puntero_expediente_id:
                await SeleccionarCorpus(obra_repo, norma_repo).ejecutar(
                    SeleccionarCorpusRequest(
                        abreviatura=norma.abreviatura,
                        propietario_id=a.propietario_id,
                        expediente_id=a.puntero_expediente_id,
                    )
                )
            print(f"  obra {a.obra_id} -> {norma.abreviatura} ({a.estado})")
    await engine.dispose()
    aviso_poblar()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
