"""rename usuario column to carnet

Revision ID: 3be43b48654a
Revises: a1c7d2e9f034
Create Date: 2026-08-02 22:30:00.000000

Identificador de login cambia de username generico a Carnet de Identidad (CI)
o Carnet Militar (CM), string alfanumerico. Sprint 1 Auth, decision D1 del plan v3.

La unicidad de la columna NO esta como UniqueConstraint inline ni unique=True en
la columna misma; esta implementada via UNIQUE INDEX separado:
    op.create_index(op.f("ix_usuario_usuario"), "usuario", ["usuario"], unique=True)
que Autogenerate de SQLAlchemy crea con nombre `ix_usuario_usuario`.

Por tanto op.alter_column NO preserva la unicidad (correccion al plan v3 de agy).
M1 necesita:
1. alter_column rename usuario->carnet
2. drop_index ix_usuario_usuario (queda apuntando a col inexistente)
3. create_index ix_usuario_carnet (nombre nuevo consistente, unique=True)
4. downgrade simetrico.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3be43b48654a"
down_revision: str | Sequence[str] | None = "a1c7d2e9f034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename columna usuario -> carnet + recreate unique index con nombre nuevo."""
    op.alter_column(
        "usuario",
        "usuario",
        new_column_name="carnet",
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.drop_index("ix_usuario_usuario", table_name="usuario")
    op.create_index("ix_usuario_carnet", "usuario", ["carnet"], unique=True)


def downgrade() -> None:
    """Revert rename carnet -> usuario + recreate unique index original."""
    op.drop_index("ix_usuario_carnet", table_name="usuario")
    op.alter_column(
        "usuario",
        "carnet",
        new_column_name="usuario",
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.create_index("ix_usuario_usuario", "usuario", ["usuario"], unique=True)
