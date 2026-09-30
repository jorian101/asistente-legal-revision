"""`alembic upgrade head` debe construir una BD vacia.

Sin esto un despliegue nuevo no puede crear el esquema:
la migracion 3b9615747950 hacia DROP de un indice que ninguna migracion anterior crea.
Requiere PostgreSQL (`make test-integration`); se omite si no hay servidor.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND = Path(__file__).resolve().parents[2]


def _admin_conn():
    from dotenv import dotenv_values

    env = {**os.environ, **dotenv_values(_BACKEND.parent / ".env")}
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(
            host="127.0.0.1",
            port=int(env.get("POSTGRES_PORT", "5432")),
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
            dbname="postgres",
            autocommit=True,
            connect_timeout=3,
        )
    except Exception as exc:  # noqa: BLE001 - sin servidor no hay test
        pytest.skip(f"PostgreSQL no disponible: {exc}")
    return conn, env


def _alembic(env: dict[str, str], db: str, *args: str) -> subprocess.CompletedProcess[str]:
    entorno = {**os.environ, **{k: v for k, v in env.items() if v is not None}}
    entorno["POSTGRES_DB"] = db
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_upgrade_head_desde_una_bd_vacia() -> None:
    conn, env = _admin_conn()
    db = f"migraciones_{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE DATABASE "{db}"')
    try:
        subir = _alembic(env, db, "upgrade", "head")
        assert subir.returncode == 0, subir.stderr[-1500:]
    finally:
        conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        conn.close()


def test_los_modelos_no_tienen_drift_con_las_migraciones() -> None:
    """`alembic check`: tipos, indices y constraints de los modelos = los de la BD migrada."""
    conn, env = _admin_conn()
    db = f"migraciones_{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE DATABASE "{db}"')
    try:
        assert _alembic(env, db, "upgrade", "head").returncode == 0
        drift = _alembic(env, db, "check")
        assert drift.returncode == 0, (drift.stdout + drift.stderr)[-2500:]
    finally:
        conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        conn.close()
