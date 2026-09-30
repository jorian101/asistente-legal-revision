"""CLI: corpus_publico.py — Paquete del corpus público para instalaciones de usuario.

    exportar <dir>   (desarrollo, contra la BD local) escribe el paquete en <dir>
    importar <dir>   (instalación de usuario) lo carga en una BD recién creada

Qué entra: solo `norma` global y activa (normas, jurisprudencia, doctrina) y sus
`fragmento`, más los puntos de Qdrant de esos fragmentos. NUNCA obras/obrados,
expedientes, usuarios, chats ni historial. Por eso no se usan snapshots de colección:
`corpus_juridico` guarda obrados junto a las normas. La jurisprudencia promovida desde
un obrado (`origen_obra_id`) tampoco entra: su texto viene de un expediente real.

Guarda: el export aborta si un fragmento o un punto trae rastro de obra/expediente.
Formato: manifiesto.json + norma.csv + fragmento.csv + qdrant/<coleccion>.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from qdrant_client import QdrantClient, models

from src.config import get_settings

COLECCIONES = ("corpus_juridico", "jurisprudencia", "doctrina")
# Columnas de `norma` que apuntan a usuarios u obras que no viajan: se exportan NULL.
ANULADAS = ("indexado_por", "propietario_id", "origen_obra_id")
FILTRO_NORMA = "estado_visibilidad = 'global' AND activo AND origen_obra_id IS NULL"
LOTE = 256


class FugaDePrivadosError(RuntimeError):
    """El paquete iba a llevar datos de obrados o expedientes."""


def validar_fragmentos(filas: list[dict[str, Any]]) -> None:
    for f in filas:
        if f.get("obra_id") is not None or f.get("expediente_id") is not None:
            raise FugaDePrivadosError(f"fragmento {f.get('id')} pertenece a una obra/expediente")


def validar_punto(coleccion: str, payload: dict[str, Any]) -> None:
    privado = (
        payload.get("obra_id") is not None
        or payload.get("expediente_id") is not None
        or payload.get("tipo_fuente") == "obra"
        or payload.get("visibilidad") not in (None, "", "global")
        or payload.get("norma_id") is None
    )
    if privado:
        raise FugaDePrivadosError(
            f"punto de {coleccion} con datos privados: {payload.get('norma_id')}"
        )


def _vector_a_json(vector: Any) -> Any:
    if isinstance(vector, dict):
        return {k: _vector_a_json(v) for k, v in vector.items()}
    if isinstance(vector, models.SparseVector):
        return {"indices": list(vector.indices), "values": list(vector.values)}
    return vector


def _vector_de_json(vector: Any) -> Any:
    if isinstance(vector, dict) and set(vector) == {"indices", "values"}:
        return models.SparseVector(**vector)
    if isinstance(vector, dict):
        return {k: _vector_de_json(v) for k, v in vector.items()}
    return vector


def _conectar() -> psycopg.Connection:
    s = get_settings()
    return psycopg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password,
        dbname=s.postgres_db,
    )


def _columnas(cur: psycopg.Cursor, tabla: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position",
        (tabla,),
    )
    return [r[0] for r in cur.fetchall()]


def _copiar_a_csv(cur: psycopg.Cursor, consulta: str, destino: Path) -> None:
    with destino.open("wb") as f, cur.copy(f"COPY ({consulta}) TO STDOUT WITH CSV HEADER") as cp:
        for bloque in cp:
            f.write(bloque)


def exportar(destino: Path) -> None:
    s = get_settings()
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "qdrant").mkdir(exist_ok=True)
    with _conectar() as conn, conn.cursor() as cur:
        cols_norma = _columnas(cur, "norma")
        select_norma = ", ".join(f"NULL AS {c}" if c in ANULADAS else c for c in cols_norma)
        _copiar_a_csv(
            cur,
            f"SELECT {select_norma} FROM norma WHERE {FILTRO_NORMA} ORDER BY id",
            destino / "norma.csv",
        )
        sub = f"SELECT id FROM norma WHERE {FILTRO_NORMA}"
        cur.execute(
            f"SELECT id, obra_id, expediente_id, qdrant_point_id FROM fragmento "
            f"WHERE norma_id IN ({sub})"
        )
        frags = [
            dict(zip(("id", "obra_id", "expediente_id", "qdrant_point_id"), r, strict=True))
            for r in cur.fetchall()
        ]
        validar_fragmentos(frags)
        _copiar_a_csv(
            cur,
            f"SELECT * FROM fragmento WHERE norma_id IN ({sub}) ORDER BY id",
            destino / "fragmento.csv",
        )
        cur.execute(
            "SELECT abreviatura FROM norma WHERE estado_visibilidad = 'global' AND activo "
            "AND origen_obra_id IS NOT NULL ORDER BY abreviatura"
        )
        excluidas = [r[0] for r in cur.fetchall()]
        cur.execute(f"SELECT count(*) FROM norma WHERE {FILTRO_NORMA}")
        n_normas = cur.fetchone()[0]  # type: ignore[index]

    # Los fragmentos padre no tienen vector (qdrant_point_id vacío).
    ids = [f["qdrant_point_id"] for f in frags if f["qdrant_point_id"]]
    client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key, timeout=60)
    puntos_por_coleccion: dict[str, int] = {}
    for coleccion in COLECCIONES:
        n = 0
        with (destino / "qdrant" / f"{coleccion}.jsonl").open("w") as f:
            for i in range(0, len(ids), LOTE):
                for p in client.retrieve(coleccion, ids=ids[i : i + LOTE], with_vectors=True):
                    validar_punto(coleccion, p.payload or {})
                    f.write(
                        json.dumps(
                            {"id": p.id, "vector": _vector_a_json(p.vector), "payload": p.payload}
                        )
                        + "\n"
                    )
                    n += 1
        puntos_por_coleccion[coleccion] = n

    manifiesto = {
        "embedding_model": s.embedding_endpoints[0]["model"],
        "embedding_dim": s.embedding_endpoints[0]["dim"],
        "normas": n_normas,
        "fragmentos": len(frags),
        "puntos": puntos_por_coleccion,
        "excluidas_promovidas_de_obrados": excluidas,
    }
    (destino / "manifiesto.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    print(json.dumps(manifiesto, indent=2, ensure_ascii=False))


def importar(origen: Path) -> None:
    s = get_settings()
    manifiesto = json.loads((origen / "manifiesto.json").read_text())
    embedder = s.embedding_endpoints[0]
    if (manifiesto["embedding_model"], manifiesto["embedding_dim"]) != (
        embedder["model"],
        embedder["dim"],
    ):
        raise SystemExit(
            f"El paquete usa {manifiesto['embedding_model']} ({manifiesto['embedding_dim']}) "
            f"y esta instalación {embedder['model']} ({embedder['dim']}): no son compatibles."
        )
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM norma")
        if cur.fetchone()[0]:  # type: ignore[index]
            print("La BD ya tiene normas: no se importa el corpus (solo va en la instalación).")
            return
        for tabla in ("norma", "fragmento"):
            archivo = origen / f"{tabla}.csv"
            cols = archivo.open().readline().strip()
            with (
                archivo.open("rb") as f,
                cur.copy(f"COPY {tabla} ({cols}) FROM STDIN WITH CSV HEADER") as cp,
            ):
                while bloque := f.read(1 << 20):
                    cp.write(bloque)
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                f"COALESCE((SELECT max(id) FROM {tabla}), 1))"
            )
        conn.commit()

    client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key, timeout=60)
    for coleccion in COLECCIONES:
        lineas = (origen / "qdrant" / f"{coleccion}.jsonl").read_text().splitlines()
        puntos = [json.loads(linea) for linea in lineas if linea]
        for i in range(0, len(puntos), LOTE):
            client.upsert(
                coleccion,
                points=[
                    models.PointStruct(
                        id=p["id"], vector=_vector_de_json(p["vector"]), payload=p["payload"]
                    )
                    for p in puntos[i : i + LOTE]
                ],
            )
        print(f"  {coleccion}: {len(puntos)} puntos")
    print(
        f"Corpus importado: {manifiesto['normas']} normas, {manifiesto['fragmentos']} fragmentos."
    )


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("exportar", "importar"):
        raise SystemExit("Uso: corpus_publico.py exportar|importar <dir>")
    (exportar if sys.argv[1] == "exportar" else importar)(Path(sys.argv[2]))
