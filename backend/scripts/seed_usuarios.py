"""CLI: seed_usuarios.py — Crea usuarios iniciales (admin/supervisor/operador).

Idempotente: si el carnet ya existe, lo saltea. Para reiniciar credenciales,
usar el endpoint PATCH /admin/usuarios/{carnet}/reset-password desde la UI.

Uso:
    cd backend && uv run python scripts/seed_usuarios.py

Variables de entorno requeridas (.env):
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT, SECRET_KEY

Credenciales por defecto (cambiar tras primer login):
    - admin01     / admin12345    (administrador)
    - sup01       / sup12345      (supervisor)
    - op01        / op12345       (operador_juridico)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bcrypt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts._aviso import aviso_poblar  # noqa: E402
from src.adapters.postgres.models.usuario import UsuarioModel
from src.config import get_settings
from src.domain.entities.usuario import RolUsuario

USUARIOS_SEED = [
    {
        "carnet": "admin01",
        "nombre": "Administrador del Sistema",
        "password": "admin12345",
        "rol": "administrador",
        # El admin no pertenece a la SAC: personal tecnico (Tabla 18).
        "cargo": "Personal Técnico",
    },
    {
        "carnet": "sup01",
        "nombre": "Supervisor de Sala",
        "password": "sup12345",
        "rol": "supervisor",
        "cargo": "Vocal Presidente",
    },
    {
        "carnet": "op01",
        "nombre": "Operador Juridico Fiscal",
        "password": "op12345",
        "rol": "operador_juridico",
        "cargo": "Fiscal",
    },
    # Cuentas QA sin 2FA (email None -> login legacy) para auditorias
    # automatizadas (browserbase-delegate Fase 5). No son usuarios reales.
    {
        "carnet": "qaadmin",
        "nombre": "QA Auditor Admin",
        "password": "qasecret123",
        "rol": "administrador",
        "cargo": "Personal Técnico",
    },
    {
        "carnet": "qaop",
        "nombre": "QA Auditor Operador",
        "password": "qasecret123",
        "rol": "operador_juridico",
        "cargo": "Fiscal",
    },
    {
        "carnet": "qasup",
        "nombre": "QA Auditor Supervisor",
        "password": "qasecret123",
        "rol": "supervisor",
        "cargo": "Vocal Presidente",
    },
]


async def _seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        for u in USUARIOS_SEED:
            existing = await session.execute(
                UsuarioModel.__table__.select().where(
                    UsuarioModel.__table__.c.carnet == u["carnet"]
                )
            )
            if existing.first() is not None:
                print(f"  skip  {u['carnet']} (ya existe)")
                continue

            password_hash = bcrypt.hashpw(u["password"].encode("utf-8"), bcrypt.gensalt()).decode(
                "utf-8"
            )

            session.add(
                UsuarioModel(
                    nombre=u["nombre"],
                    carnet=u["carnet"],
                    password_hash=password_hash,
                    rol=cast(RolUsuario, u["rol"]),
                    cargo=u["cargo"],
                    activo=True,
                )
            )
            print(f"  crea  {u['carnet']} ({u['rol']}, cargo={u['cargo']})")

        await session.commit()

    await engine.dispose()
    print("Seed completo.")
    aviso_poblar()


if __name__ == "__main__":
    asyncio.run(_seed())
