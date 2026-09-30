"""Base declarativa unica para todos los modelos SQLAlchemy del adapter Postgres.

Patron Clean Architecture: la unica clase Base del adapter. Todos los modelos
deben heredar de ella. Alembic usa `Base.metadata` para autogenerar migraciones.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Clase base declarativa compartida por todos los modelos ORM."""
