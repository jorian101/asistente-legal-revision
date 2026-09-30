"""CLI: seed_criterio_vault.py — Sincroniza el criterio del vault a la BD.

Plan A (conectar el vault a Valnor): lee `wiki/criterio-vocal/` del vault
Obsidian y crea/actualiza obras con `tipo_documento='criterio'` (texto
editable en el módulo admin Criterios).

Idempotente: por cada nota calcula un hash SHA-256 del contenido; si la obra
ya existe con ese hash, no hace nada. Si cambió (la skill de extracción
actualizó el vault), la actualiza.

Uso:
    uv run python scripts/seed_criterio_vault.py [--vault <ruta>] [--propietario 4]

Requiere stack levantado (PG + Qdrant + Ollama para indexar). El texto del
criterio se guarda en obra.contenido_texto (no se indexa por defecto — es
instrucción de comportamiento, Plan D lo inyecta al prompt).
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
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.config import get_settings
from src.domain.entities.obra import Obra
from src.domain.services.criterio_texto import strip_frontmatter

_DEFAULT_VAULT = Path("/home/jorian/proyectos/asistente-legal-vault/wiki/criterio-vocal")
_PROPIETARIO_DEFAULT = int(
    os.environ.get("SEED_PROPIETARIO_ID", "26")
)  # 26 = 10702181 (supervisor)


def _hash_nota(contenido: str) -> str:
    """Hash del contenido normalizado (para detectar cambios)."""
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", type=Path, default=_DEFAULT_VAULT)
    ap.add_argument("--propietario", type=int, default=_PROPIETARIO_DEFAULT)
    args = ap.parse_args()

    if not args.vault.exists():
        print(f"❌ Vault no encontrado: {args.vault}")
        return 1

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    obra_repo = get_obra_repo(session)

    notas = sorted(args.vault.glob("*.md"))
    # Plan D (D2): excluir MOC/perfil — no son criterio de comportamiento.
    # indice.md es un índice y perfil-vocal.md es contexto del usuario; el
    # criterio a inyectar en prompts son las notas sustantivas.
    notas = [n for n in notas if n.stem not in {"indice", "perfil-vocal"}]
    print(f"📚 Notas de criterio en vault: {len(notas)}")
    creadas = 0
    actualizadas = 0
    sin_cambio = 0

    for nota in notas:
        contenido = nota.read_text(encoding="utf-8")
        h = _hash_nota(contenido)
        slug = nota.stem  # ej. 'criterio-argumentacion'
        # Se guarda el cuerpo SIN el frontmatter YAML: el frontmatter es
        # metadato del vault (title/sources/tags) y no debe llegar ni al
        # prompt del LLM ni a la UI de Criterios.
        cuerpo = strip_frontmatter(contenido)

        # ¿Ya existe una obra criterio con este slug?
        existentes = await obra_repo.listar_criterios()
        existente = next((o for o in existentes if o.nombre_archivo == f"{slug}.md"), None)

        if existente is not None:
            # ¿Cambió? El hash vive en el texto (o en procedencia si se editó).
            hash_actual = existente.procedencia or ""
            if hash_actual == h:
                sin_cambio += 1
                continue
            # Actualizar contenido + nuevo hash.
            await obra_repo.actualizar_criterio(
                obra_id=existente.id,  # type: ignore[arg-type]
                contenido_texto=cuerpo,
                procedencia=h,
            )
            actualizadas += 1
            continue

        obra = Obra(
            id=None,
            expediente_id=None,  # criterio global, sin expediente
            propietario_id=args.propietario,
            tipo_documento="criterio",
            nombre_archivo=f"{slug}.md",
            contenido_texto=cuerpo,
            ruta_archivo=None,
            fojas_inicio=None,
            fojas_fin=None,
            estado_visibilidad="global",
            fuente="generado_sistema",
            tamano_archivo=len(contenido.encode("utf-8")),
            estado_procesamiento="completado",
            autor_instancia="vault/wiki/criterio-vocal",
            autor="Vocal (criterio-vocal)",
            procedencia=h,  # hash de detección de cambios
            recomendada=True,
        )
        await obra_repo.guardar(obra)
        creadas += 1

    await session.close()
    await engine.dispose()
    print(
        f"✅ Criterios: {creadas} creadas, {actualizadas} actualizadas, {sin_cambio} sin cambios."
    )
    aviso_poblar()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
