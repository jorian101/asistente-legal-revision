"""CLI: seed_casos_tsjm.py — Carga casos reales TSJM desde el vault.

Seed de datos de casos reales del TSJM (consultas y apelaciones) desde el
vault Obsidian para habilitar la generacion E2E de borradores. Crea:
- Expediente (numero_caso, tipo_proceso, datos de identificacion).
- Obras del caso (sentencia, relacion, dictamen, memorial, etc.) con
  contenido real del vault.
- Indexa las obras en Qdrant via IndexarObra (Regla 5: propietario + privado).

Uso:
    uv run python scripts/seed_casos_tsjm.py --caso 3349
    uv run python scripts/seed_casos_tsjm.py --caso 3145
    uv run python scripts/seed_casos_tsjm.py --caso todos

Requiere stack levantado (PG 5433 + Qdrant 6333 + Ollama 11434). Idempotente:
si el expediente ya existe, no hace nada.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
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
from src.domain.entities.expediente import Expediente
from src.domain.entities.obra import Obra

_VAULT_ROOT = Path("/home/jorian/proyectos/asistente-legal-vault/sources/casos-tsjm/casos")

_PROPIETARIO = int(os.environ.get("SEED_PROPIETARIO_ID", "26"))  # 26 = 10702181 (supervisor)
_ABIERTA_POR = _PROPIETARIO


# Config por caso: numero_caso en BD, datos del expediente y obras.
# Cada obra: (tipo_documento, nombre_archivo, archivo_relativo, fojas_i, fojas_f)
_CASOS: dict[str, dict] = {
    "3349": {
        "numero_caso": "3349",
        "tipo_proceso": "consulta",
        "tribunal_origen": "TRIBUNAL PERMANENTE DE JUSTICIA MILITAR (TPJM)",
        "procesado_nombre": "HERLAN BORIZ CONTRERAS SAAVEDRA",
        "procesado_grado": "TCNL. INF.",
        "delito": "USO DE DOCUMENTOS FALSOS (Art. 178 Num. 3 CPM)",
        "sentencia_origen": "SENTENCIA Nº 24/2025 (15/10/2025) ABSOLUTORIA",
        "fojas_total": 639,
        "dir": "exp-3349-consulta/documentos",
        "obras": [
            ("sentencia", "sentencia_24_2025.txt", "auto_de_vista_3349.md", 600, 605),
            (
                "relacion_obrados",
                "relacion_obrados_3349.md",
                "relacion_obrados_3349.md",
                1,
                639,
            ),
            (
                "dictamen_fondo",
                "dictamen_fondo_3349.txt",
                "dictamen_fondo_3349.txt",
                643,
                644,
            ),
            # Piezas de entrada reconstruidas (vault, con nota de procedencia):
            # el guard de generación las exige (taxonomía A) y su contenido ya
            # estaba narrado en el auto de vista / relación de obrados.
            (
                "oficio_elevacion",
                "oficio_elevacion_3349.txt",
                "oficio_elevacion_3349.txt",
                613,
                613,
            ),
            (
                "acta_audiencia",
                "acta_audiencia_lectura_3349.txt",
                "acta_audiencia_lectura_3349.txt",
                598,
                599,
            ),
        ],
    },
    "9999": {
        "numero_caso": "9999",
        "tipo_proceso": "apelacion_incidental",
        "tribunal_origen": "TRIBUNAL PERMANENTE DE JUSTICIA MILITAR (TPJM)",
        "procesado_nombre": "MARCOS BENJAMIN SALINAS MIRANDA",
        "procesado_grado": "TN. CGON.",
        "delito": (
            "ABANDONO DE SERVICIO, VIOLACION DE NORMAS, FALSEDAD DE RELACION, INJURIAS A SUPERIORES"
        ),
        "sentencia_origen": "RESOLUCION Nº 17/2025 (12/11/2025) Auto Interlocutorio",
        "fojas_total": None,
        "dir": "exp-3145-3172-apelacion-incidental/documentos",
        "obras": [
            (
                "auto_interlocutorio",
                "resolucion_17_2025.txt",
                "resolucion_17_2025.txt",
                1941,
                1949,
            ),
            (
                "memorial_apelacion",
                "memorial_apelacion.txt",
                "memorial_apelacion.txt",
                1967,
                1983,
            ),
            (
                "requerimiento_fiscal",
                "requerimiento_fiscal.txt",
                "requerimiento_fiscal.txt",
                None,
                None,
            ),
            (
                "dictamen_fondo",
                "dictamen_apelacion_incidental.md",
                "dictamen_apelacion_incidental.md",
                1849,
                1991,
            ),
            (
                "auto_vista",
                "auto_de_vista_04_2026.md",
                "auto_de_vista_04_2026.md",
                None,
                None,
            ),
            # Oficio de elevación reconstruido (narrado en el dictamen de
            # apelación incidental, fs. 1991). Única pieza faltante del caso.
            (
                "oficio_elevacion",
                "oficio_elevacion_3145.txt",
                "oficio_elevacion_3145.txt",
                1991,
                1991,
            ),
        ],
    },
    "3352": {
        "numero_caso": "3352",
        "tipo_proceso": "consulta",
        "tribunal_origen": "TRIBUNAL PERMANENTE DE JUSTICIA MILITAR (TPJM)",
        "procesado_nombre": "JIMENA HINOJOSA SILES",
        "procesado_grado": "SGTO. INCL. ING.",
        "delito": "ABANDONO DE SERVICIO (Art. 140 CPM)",
        "sentencia_origen": "SENTENCIA Nº 28/2025 (29/11/2025) ABSOLUTORIA",
        # Cuerpo 1 fs 001-200, Cuerpo 2 fs 201-452, Cuerpo 3 fs 453-470
        # (dictamen_radicatoria_3352.md).
        "fojas_total": 470,
        "dir": "exp-3352-consulta/documentos",
        # Solo inputs previos a la radicatoria. NO indexar
        # dictamen_radicatoria_3352.md ni auto_de_vista_11_2026.md: son
        # outputs reales del flujo y contaminarian la comparacion
        # generacion-vs-real (el LLM copiaria del documento a evaluar).
        "obras": [
            (
                "sentencia",
                "sentencia_hinojosa.txt",
                "sentencia_hinojosa.txt",
                424,
                428,
            ),
            (
                "relacion_obrados",
                "obrados_hinojosa.md",
                "obrados_hinojosa.md",
                1,
                470,
            ),
            # Piezas de entrada reconstruidas: oficio narrado en la relación
            # (fs. 453), acta narrada en el dictamen de radicatoria
            # (fs. 420-421). Sin ellas el guard de generación bloquea.
            (
                "oficio_elevacion",
                "oficio_elevacion_3352.txt",
                "oficio_elevacion_3352.txt",
                453,
                453,
            ),
            (
                "acta_audiencia",
                "acta_audiencia_lectura_3352.txt",
                "acta_audiencia_lectura_3352.txt",
                420,
                421,
            ),
        ],
    },
}


def _elegir_casos(arg: str) -> list[str]:
    if arg == "todos":
        return list(_CASOS.keys())
    if arg not in _CASOS:
        raise SystemExit(f"❌ Caso desconocido: {arg}. Disponibles: {list(_CASOS)} o 'todos'.")
    return [arg]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed de casos reales TSJM")
    parser.add_argument(
        "--caso",
        default="3349",
        help="Caso a cargar: 3349, 3145, 3352 o 'todos' (default: 3349)",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            expediente_repo = get_expediente_repo(session)
            obra_repo = get_obra_repo(session)

            for numero in _elegir_casos(args.caso):
                cfg = _CASOS[numero]
                existente = await expediente_repo.obtener_por_numero_caso(cfg["numero_caso"])
                if existente is not None:
                    exp_id = existente.id
                    print(f"ℹ️  Expediente {cfg['numero_caso']} ya existe (id={exp_id}).")
                    # P3: reconciliar `delito` si quedó desactualizado (p.ej. un
                    # código snake_case de una siembra vieja, previo a que este
                    # script empezara a guardar el texto legible del auto real).
                    # `{{DELITO_CONCRETO}}`/`{{DELITOS}}` de las plantillas leen
                    # este campo directo — sin esto, "ya existe" lo dejaba fijo
                    # para siempre aunque el seed ya tuviera el valor correcto.
                    if existente.delito != cfg["delito"]:
                        await expediente_repo.actualizar(exp_id, delito=cfg["delito"])
                        await session.commit()
                        print(
                            f"   🩹 delito desactualizado: "
                            f"{existente.delito!r} -> {cfg['delito']!r}"
                        )
                    # Reanudación: indexar obras pendientes/faltantes.
                    obras_existentes = await obra_repo.listar_por_expediente(exp_id, _PROPIETARIO)
                    por_nombre = {o.nombre_archivo: o for o in obras_existentes}
                    # P5.6: limpiar obras huérfanas (procesando/fallido que no
                    # corresponden a ninguna obra del caso) — restos de seeds
                    # interrumpidos que duplicarían o ensuciarían el expediente.
                    nombres_validos = {nombre for _, nombre, *_ in cfg["obras"]}
                    for obra in obras_existentes:
                        if (
                            obra.nombre_archivo not in nombres_validos
                            and obra.estado_procesamiento in ("procesando", "fallido")
                        ):
                            eliminada = await obra_repo.eliminar(obra.id)
                            await session.commit()
                            print(
                                f"   🧹 Obra huérfana '{obra.nombre_archivo}' "
                                f"id={obra.id} eliminada={eliminada}"
                            )
                    indexador = IndexarObra(
                        obra_repo=obra_repo,
                        fragmento_repo=FragmentoRepoImpl(session),
                        embedder=build_embedder(None),
                        vector_repo=QdrantCorpusRepo(),
                    )
                    dir_caso = _VAULT_ROOT / cfg["dir"]
                    for tipo, nombre, archivo, f_i, f_f in cfg["obras"]:
                        obra_existente = por_nombre.get(nombre)
                        en_progreso = (
                            obra_existente is not None
                            and obra_existente.estado_procesamiento in ("completado", "procesando")
                        )
                        if en_progreso and obra_existente.estado_procesamiento == "completado":
                            linea = (
                                f"   ➖ Obra '{tipo}' ya completa (id={obra_existente.id}). Skip."
                            )
                            print(linea)
                            continue
                        if not (dir_caso / archivo).exists():
                            print(f"⚠️  No existe {dir_caso / archivo}. Saltando {tipo}.")
                            continue
                        contenido = (dir_caso / archivo).read_text(encoding="utf-8")
                        obra = Obra(
                            id=obra_existente.id if obra_existente else None,
                            expediente_id=exp_id,
                            propietario_id=_PROPIETARIO,
                            tipo_documento=tipo,  # type: ignore[arg-type]
                            nombre_archivo=nombre,
                            contenido_texto=contenido,
                            ruta_archivo=str(dir_caso / archivo),
                            fojas_inicio=f_i,
                            fojas_fin=f_f,
                            estado_visibilidad="privado",
                            fuente="carga_usuario",
                            tamano_archivo=len(contenido.encode("utf-8")),
                            estado_procesamiento="pendiente",
                        )
                        obra_guardada = await obra_repo.guardar(obra)
                        await session.commit()
                        print(f"   📄 Reanudando obra '{tipo}' id={obra_guardada.id}")
                        resp = await indexador.ejecutar(obra_guardada)
                        await session.commit()
                        print(
                            f"      → {resp.fragmentos_creados} fragmentos, "
                            f"{resp.vectores_indexados} vectores"
                        )
                    print(f"\n✅ EXP-{cfg['numero_caso']} verificado/completado.")
                    continue

                expediente = Expediente(
                    id=None,
                    numero_caso=cfg["numero_caso"],
                    tipo_proceso=cfg["tipo_proceso"],
                    tribunal_origen=cfg["tribunal_origen"],
                    procesado_nombre=cfg["procesado_nombre"],
                    procesado_grado=cfg["procesado_grado"],
                    delito=cfg["delito"],
                    sentencia_origen=cfg["sentencia_origen"],
                    fojas_total=cfg["fojas_total"],
                    estado="activo",
                    abierto_por=_ABIERTA_POR,
                    created_at=datetime.now(),
                )
                guardado = await expediente_repo.guardar(expediente)
                await session.commit()
                print(f"✅ Expediente {cfg['numero_caso']} creado (id={guardado.id})")

                indexador = IndexarObra(
                    obra_repo=obra_repo,
                    fragmento_repo=FragmentoRepoImpl(session),
                    embedder=build_embedder(None),
                    vector_repo=QdrantCorpusRepo(),
                )

                dir_caso = _VAULT_ROOT / cfg["dir"]
                for tipo, nombre, archivo, f_i, f_f in cfg["obras"]:
                    ruta = dir_caso / archivo
                    if not ruta.exists():
                        print(f"⚠️  No existe {ruta}. Saltando {tipo}.")
                        continue
                    contenido = ruta.read_text(encoding="utf-8")
                    obra = Obra(
                        id=None,
                        expediente_id=guardado.id,
                        propietario_id=_PROPIETARIO,
                        tipo_documento=tipo,  # type: ignore[arg-type]
                        nombre_archivo=nombre,
                        contenido_texto=contenido,
                        ruta_archivo=str(ruta),
                        fojas_inicio=f_i,
                        fojas_fin=f_f,
                        estado_visibilidad="privado",
                        fuente="carga_usuario",
                        tamano_archivo=len(contenido.encode("utf-8")),
                        estado_procesamiento="pendiente",
                    )
                    obra_guardada = await obra_repo.guardar(obra)
                    await session.commit()
                    print(f"   📄 Obra '{tipo}' id={obra_guardada.id}")

                    resp = await indexador.ejecutar(obra_guardada)
                    await session.commit()
                    linea = (
                        f"      → {resp.fragmentos_creados} fragmentos, "
                        f"{resp.vectores_indexados} vectores"
                    )
                    print(linea)

                print(f"\n✅ EXP-{cfg['numero_caso']} cargado e indexado.")
    finally:
        await engine.dispose()

    aviso_poblar()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
