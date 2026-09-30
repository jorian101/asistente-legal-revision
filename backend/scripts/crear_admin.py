"""CLI: crear_admin.py — Primer administrador de una instalación de usuario.

A diferencia de seed_usuarios.py (claves fijas de desarrollo), genera una contraseña
aleatoria y la imprime UNA sola vez; se cambia después desde el perfil. Idempotente:
si ya hay algún administrador, no hace nada.

Uso (lo llama instalar.sh):
    python scripts/crear_admin.py
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.postgres.models.usuario import UsuarioModel
from src.config import get_settings

CARNET = "admin"


async def crear_admin() -> str | None:
    """Crea el admin si no hay ninguno; devuelve la contraseña generada o None."""
    engine = create_async_engine(get_settings().postgres_url_async, echo=False)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            existe = await session.scalar(
                select(UsuarioModel.id).where(UsuarioModel.rol == "administrador").limit(1)
            )
            if existe is not None:
                return None
            password = secrets.token_urlsafe(12)
            session.add(
                UsuarioModel(
                    nombre="Administrador",
                    carnet=CARNET,
                    password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                    rol="administrador",
                    cargo="Personal Técnico",
                    activo=True,
                )
            )
            await session.commit()
            return password
    finally:
        await engine.dispose()


if __name__ == "__main__":
    password = asyncio.run(crear_admin())
    if password is None:
        print("Ya existe un administrador: no se creó otro.")
    else:
        print(f"Administrador creado. Usuario: {CARNET}  Contraseña: {password}")
        print("Guardala ahora (no se vuelve a mostrar) y cambiala desde tu perfil.")
