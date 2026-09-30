"""CLI: seed_doctrina_vault.py — Carga doctrina del vault + vincula a casos.

Plan B (conectar el vault a Valnor). Dos fases:

1. **Casos ejemplo** (reusa seed_casos_tsjm): 3145/3172 y 3349 se re-sembran
   con su MISMO numero_caso y sus documentos (obras del expediente).

2. **Doctrina del vault**: cada ficha de `sources/doctrina/raw/*.txt` se carga
   como obra `tipo_documento=doctrina` (solo doctrina; las sentencias son norma):
   - Si hay caso relacionado (matriz wiki/relaciones/doctrina-casos.md) ->
     obra con `expediente_id` del caso, estado 'publicado'.
   - Si no -> obra sin expediente, estado 'global' (indexable en consultas).

Idempotente: por doctrina calcula hash SHA-256 del contenido; si la obra ya
existe con ese hash, skip. Los casos los maneja seed_casos_tsjm (idempotente).

Uso:
    uv run python scripts/seed_doctrina_vault.py
    uv run python scripts/seed_doctrina_vault.py --solo-doctrina

Requiere stack levantado (PG + Qdrant + Ollama para indexar).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts._aviso import aviso_poblar  # noqa: E402
from src.adapters.http.dependencies import build_embedder
from src.adapters.postgres.repos.expediente_repo import get_expediente_repo
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.application.expedientes.indexar_obra import IndexarObra
from src.config import get_settings
from src.domain.entities.obra import Obra

_VAULT_RAW = Path("/home/jorian/proyectos/asistente-legal-vault/sources/doctrina/raw")
_PROPIETARIO = int(os.environ.get("SEED_PROPIETARIO_ID", "26"))  # 26 = 10702181 (supervisor)

# Doctrina del vault: fuente cruda + metadatos + casos relacionados (matriz).
# casos_relacionados: numero_caso -> estado con que se vincula al expediente.
_DOCTRINA: list[dict] = [
    # Las sentencias (SCP, SC, Corte IDH) son jurisprudencia: viven como norma
    # (scripts/indexar_jurisprudencia.py), no como obra doctrina.
    {
        "archivo": "doctrina-apelacion-incidental.txt",
        "autor": "Doctrina procesal penal (Ley 1970)",
        "fecha": "",
        "procedencia": "Doctrina — apelación incidental (supletoria Ley 1970)",
        "naturaleza": "doctrinal",
        "recomendada": False,
        # Matriz: se usa en Salinas (3145/3172). Va con ese expediente.
        "casos_relacionados": {"9999": "publicado"},
    },
]


def _hash_contenido(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


async def _sembrar_casos() -> None:
    """Re-sembra los 2 casos ejemplo con su MISMO numero_caso."""
    import subprocess

    r = subprocess.run(
        [sys.executable, "-m", "scripts.seed_casos_tsjm", "--caso", "todos"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        raise SystemExit(f"seed_casos_tsjm falló (exit {r.returncode})")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--solo-doctrina", action="store_true", help="Solo doctrina, sin re-sembrar casos"
    )
    args = ap.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    if not args.solo_doctrina:
        print("📁 Re-sembrando casos ejemplo (3145/3172 + 3349)...")
        await _sembrar_casos()

    creadas = 0
    actualizadas = 0
    sin_cambio = 0

    async with session_factory() as session:
        obra_repo = get_obra_repo(session)
        expediente_repo = get_expediente_repo(session)
        indexador = IndexarObra(
            obra_repo=obra_repo,
            fragmento_repo=FragmentoRepoImpl(session),
            embedder=build_embedder(None),
            vector_repo=QdrantCorpusRepo(),
        )

        # Mapa numero_caso -> expediente_id (para vincular doctrina).
        exp_por_numero: dict[str, int | None] = {}
        for cfg in ({"numero_caso": "9999"}, {"numero_caso": "3349"}):
            e = await expediente_repo.obtener_por_numero_caso(cfg["numero_caso"])
            exp_por_numero[cfg["numero_caso"]] = e.id if e else None
            print(f"ℹ️  Expediente {cfg['numero_caso']} -> id={exp_por_numero[cfg['numero_caso']]}")

        # Doctrinas ya existentes (para idempotencia por nombre_archivo).
        doctrinas_existentes = await obra_repo.listar_por_estado("global")
        por_archivo = {o.nombre_archivo: o for o in doctrinas_existentes}
        # También buscar vinculadas a los expedientes (publicado).
        for _numero, exp_id in exp_por_numero.items():
            if exp_id is None:
                continue
            obras_exp = await obra_repo.listar_por_expediente(exp_id, _PROPIETARIO)
            for o in obras_exp:
                por_archivo.setdefault(o.nombre_archivo, o)

        for cfg in _DOCTRINA:
            ruta = _VAULT_RAW / cfg["archivo"]
            if not ruta.exists():
                print(f"⚠️  No existe {ruta}. Saltando.")
                continue
            contenido = ruta.read_text(encoding="utf-8")
            h = _hash_contenido(contenido)

            # ¿Con qué expediente va (si hay caso relacionado presente)?
            expediente_id = None
            estado = "global"
            for _numero, est in cfg["casos_relacionados"].items():
                if exp_por_numero.get(_numero):
                    expediente_id = exp_por_numero[_numero]
                    estado = est
                    break

            existente = por_archivo.get(cfg["archivo"])
            if existente is not None:
                if (existente.procedencia or "") == h:
                    sin_cambio += 1
                    continue
                await obra_repo.actualizar_criterio(
                    obra_id=existente.id,  # type: ignore[arg-type]
                    contenido_texto=contenido,
                    procedencia=h,
                )
                actualizadas += 1
                continue

            obra = Obra(
                id=None,
                expediente_id=expediente_id,
                propietario_id=_PROPIETARIO,
                tipo_documento="doctrina",
                nombre_archivo=cfg["archivo"],
                contenido_texto=contenido,
                ruta_archivo=str(ruta),
                fojas_inicio=None,
                fojas_fin=None,
                estado_visibilidad=estado,
                fuente="generado_sistema",
                tamano_archivo=len(contenido.encode("utf-8")),
                estado_procesamiento="pendiente",
                autor_instancia=cfg["procedencia"],
                autor=cfg["autor"],
                fecha_documento=cfg["fecha"],
                procedencia=h,
                recomendada=cfg["recomendada"],
            )
            guardada = await obra_repo.guardar(obra)
            await session.commit()
            await obra_repo.actualizar_estado_procesamiento(guardada.id, "pendiente")
            await indexador.ejecutar(guardada)
            await session.commit()
            destino = f"expediente {expediente_id}" if expediente_id else "global"
            print(f"   📄 {cfg['archivo']} -> {destino} ({estado}) id={guardada.id}")
            creadas += 1

    await engine.dispose()
    print(f"✅ Doctrina: {creadas} creadas, {actualizadas} actualizadas, {sin_cambio} sin cambios.")
    aviso_poblar()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
