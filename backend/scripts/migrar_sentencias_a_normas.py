"""CLI: migrar_sentencias_a_normas.py — saca las sentencias de la doctrina.

`seed_doctrina_vault.py` sembró SCP 0623/2024-S4, SCP 0663/2025-S2 y la Corte IDH
(Tribunal Constitucional vs Perú) como obras `tipo_documento=doctrina`, ademas de
existir como norma (`jerarquia=jurisprudencia`). Cada sentencia quedaba duplicada
en Qdrant (`corpus_juridico`) y aparecia como doctrina/obrado.

Por cada una (solo si su norma esta indexada y activa):
- obra de expediente -> puntero a la norma (`corpus=jurisprudencia`, `corpus_ref`),
  sin contenido ni fragmentos propios;
- obra global (sin expediente) -> se desactiva (la norma se selecciona/recomienda
  como cualquier sentencia del corpus).
En ambos casos se borran sus fragmentos de PG y sus puntos de `corpus_juridico`.

Por defecto solo muestra el plan (dry-run). `--aplicar` ejecuta y guarda antes un
respaldo JSON de las obras afectadas.

Uso:
    uv run python scripts/migrar_sentencias_a_normas.py
    uv run python scripts/migrar_sentencias_a_normas.py --aplicar
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

# Archivo de la obra sembrada -> abreviatura de la norma equivalente.
SENTENCIAS: dict[str, str] = {
    "scp-0623-2024-s4.txt": "SCP-0623-2024-S4",
    "scp-0663-2025-s2.txt": "SCP-0663-2025-S2",
    "corte-idh-tc-peru.txt": "CIDH-TC-PERU-2001",
}


@dataclass(frozen=True)
class Accion:
    obra_id: int
    accion: str  # "puntero" | "desactivar"
    abreviatura: str


def planificar(
    obras, abreviaturas_indexadas: set[str], solo_obra: int | None = None
) -> list[Accion]:
    """Plan puro: que obras `doctrina` son en realidad sentencias ya indexadas como norma."""
    plan: list[Accion] = []
    for o in obras:
        abreviatura = SENTENCIAS.get(o.nombre_archivo)
        if solo_obra is not None and o.id != solo_obra:
            continue
        if (
            abreviatura is None
            or o.tipo_documento != "doctrina"
            or not o.activo
            or abreviatura not in abreviaturas_indexadas
        ):
            continue
        plan.append(
            Accion(o.id, "puntero" if o.expediente_id is not None else "desactivar", abreviatura)
        )
    return plan


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="ejecuta (por defecto solo plan)")
    ap.add_argument("--obra", type=int, help="migra solo esa obra (paso a paso)")
    args = ap.parse_args()

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from scripts._aviso import aviso_poblar
    from src.adapters.postgres.models.norma import NormaModel
    from src.adapters.postgres.models.obra import ObraModel
    from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
    from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
    from src.config import get_settings

    engine = create_async_engine(get_settings().postgres_url_async)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        obras = (
            (await session.execute(select(ObraModel).where(ObraModel.tipo_documento == "doctrina")))
            .scalars()
            .all()
        )
        normas = set(
            (
                await session.execute(
                    select(NormaModel.abreviatura).where(
                        NormaModel.activo.is_(True), NormaModel.indexado.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        plan = planificar(obras, normas, solo_obra=args.obra)
        if not plan:
            print("Nada que migrar.")
            await engine.dispose()
            return 0
        for a in plan:
            print(f"  obra {a.obra_id}: {a.accion} -> {a.abreviatura}")
        if not args.aplicar:
            print("Dry-run: usa --aplicar para ejecutar (guarda respaldo JSON antes).")
            await engine.dispose()
            return 0

        respaldo = Path(f"respaldo-sentencias-{datetime.now(UTC):%Y%m%d-%H%M%S}.json")
        por_id = {o.id: o for o in obras}
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

        vector = QdrantCorpusRepo()
        fragmentos = FragmentoRepoImpl(session)
        for a in plan:
            await vector.delete_by_obra(a.obra_id)
            await fragmentos.delete_by_obra(a.obra_id)
            if a.accion == "puntero":
                await session.execute(
                    update(ObraModel)
                    .where(ObraModel.id == a.obra_id)
                    .values(
                        tipo_documento="jurisprudencia",
                        corpus="jurisprudencia",
                        corpus_ref=a.abreviatura,
                        contenido_texto="",
                        estado_procesamiento="completado",
                    )
                )
            else:
                await session.execute(
                    update(ObraModel).where(ObraModel.id == a.obra_id).values(activo=False)
                )
        await session.commit()
    await engine.dispose()
    print(f"Migradas {len(plan)} obras.")
    aviso_poblar()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
