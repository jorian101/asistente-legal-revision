"""CLI: seed_jurisprudencia_citada.py — Indexa el catálogo de sentencias citadas.

Plan B: lee `wiki/relaciones/jurisprudencia-citada.md` del vault (el catálogo
de SCP/SC del TCP y casos de la Corte IDH citados en los expedientes reales)
y crea obras `tipo_documento=doctrina` (estado 'global') para que el asistente
CONOZCA qué jurisprudencia citar y PARA QUÉ, sin alucinar su contenido.

Cada obra: nombre_archivo = "<sentencia>.txt", contenido_texto = la ficha
(sentencia + caso/documento + para qué) del catálogo.

Idempotente: hash del contenido en procedencia. La re-extracción del vault
(con la skill) actualiza el catálogo; este seed sincroniza a la BD.

Uso:
    uv run python scripts/seed_jurisprudencia_citada.py

Requiere PG (no indexa vectores — es criterio de cita, Plan D lo usa).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts._aviso import aviso_poblar  # noqa: E402
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.config import get_settings
from src.domain.entities.obra import Obra

_VAULT_CATALOGO = Path(
    "/home/jorian/proyectos/asistente-legal-vault/wiki/relaciones/jurisprudencia-citada.md"
)
_PROPIETARIO = int(os.environ.get("SEED_PROPIETARIO_ID", "26"))  # 26 = 10702181 (supervisor)


def _parsear_catalogo(texto: str) -> list[dict]:
    """Extrae (sentencia, caso, para_que) de las tablas del catálogo.

    Iteración por línea: separa celdas por '|'. Si la fila tiene 3 celdas ->
    sentencia | caso | para_que. Si tiene 2 -> sentencia | para_que.
    """
    fichas: list[dict] = []
    vistos: set[str] = set()
    for line in texto.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        celdas = [c.strip() for c in line.strip("|").split("|")]
        if len(celdas) < 2:
            continue
        # Normalizar negritas sobrantes en la primera celda.
        sentencia_raw = celdas[0].strip()
        # Eliminar '**' residuales del nombre (p. ej. '**SC 0092/2006-R**').
        sentencia_raw = re.sub(r"\*+", "", sentencia_raw).strip()
        if not sentencia_raw or sentencia_raw.lower() in ("(búsqueda)", "—", "-", "sentencia"):
            continue
        if len(celdas) >= 3:
            caso = celdas[1].strip().strip("*").strip()
            para_que = celdas[2].strip().strip("*").strip()
        else:
            caso = ""
            para_que = celdas[1].strip().strip("*").strip()
        # Saltar filas que no son realmente una sentencia (encabezados).
        if not re.match(r"^(SCP?|SC|AS|Caso|Corte IDH)", sentencia_raw):
            continue
        if sentencia_raw.lower() in ("sentencia", "caso", "scp / sc", "scp/sc"):
            continue
        # Normalizar: algunas filas agrupan varias sentencias separadas por comas.
        partes = [s.strip() for s in re.split(r",(?=\s*(?:SCP?|AS|Caso)\b)", sentencia_raw)]
        for p in partes:
            p = p.strip(" ,*")
            if not p or p.lower() in ("(búsqueda)", "—", "-"):
                continue
            clave = p.lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            fichas.append(
                {
                    "sentencia": p,
                    "caso": caso,
                    "para_que": para_que,
                    "contenido": (
                        f"Sentencia: {p}\n"
                        f"Caso/documento donde se cita: {caso}\n"
                        f"Para qué: {para_que}\n"
                    ),
                }
            )
    return fichas


def _hash_contenido(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


async def main() -> int:
    if not _VAULT_CATALOGO.exists():
        print(f"❌ Catálogo no encontrado: {_VAULT_CATALOGO}")
        return 1

    texto = _VAULT_CATALOGO.read_text(encoding="utf-8")
    fichas = _parsear_catalogo(texto)
    print(f"📚 Sentencias extraídas del catálogo: {len(fichas)}")

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    creadas = 0
    actualizadas = 0
    sin_cambio = 0

    async with session_factory() as session:
        obra_repo = get_obra_repo(session)
        existentes = await obra_repo.listar_por_estado("global")
        por_archivo = {
            o.nombre_archivo: o
            for o in existentes
            if o.tipo_documento == "doctrina" and o.nombre_archivo.startswith("citada-")
        }

        for f in fichas:
            slug = re.sub(r"[^a-z0-9]+", "-", f["sentencia"].lower()).strip("-")
            nombre = f"citada-{slug[:40]}.txt"
            h = _hash_contenido(f["contenido"])
            existente = por_archivo.get(nombre)
            if existente is not None:
                if (existente.procedencia or "") == h:
                    sin_cambio += 1
                    continue
                await obra_repo.actualizar_criterio(
                    obra_id=existente.id,  # type: ignore[arg-type]
                    contenido_texto=f["contenido"],
                    procedencia=h,
                )
                actualizadas += 1
                continue

            obra = Obra(
                id=None,
                expediente_id=None,
                propietario_id=_PROPIETARIO,
                tipo_documento="doctrina",
                nombre_archivo=nombre,
                contenido_texto=f["contenido"],
                ruta_archivo=None,
                fojas_inicio=None,
                fojas_fin=None,
                estado_visibilidad="global",
                fuente="generado_sistema",
                tamano_archivo=len(f["contenido"].encode("utf-8")),
                estado_procesamiento="completado",
                autor_instancia="vault/wiki/relaciones/jurisprudencia-citada",
                autor="Catálogo de jurisprudencia citada",
                procedencia=h,
                recomendada=True,
            )
            await obra_repo.guardar(obra)
            creadas += 1
            print(f"   📄 {f['sentencia']}")

    await engine.dispose()
    print(
        f"✅ Jurisprudencia citada: {creadas} creadas, {actualizadas} actualizadas, "
        f"{sin_cambio} sin cambios."
    )
    aviso_poblar()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
