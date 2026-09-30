"""add columna layout a borrador (dual md + fiel)

Almacena el layout fiel por bloque (align/bold/size/font/heading)
editado en Mis Borradores con las herramientas de Formatos.
Null = borrador sin edicion fiel (usa heuristica sobre contenido).

Revision ID: b4c5d6e7f8a9
Revises: 57330097db35
Create Date: 2026-08-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "57330097db35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "borrador",
        sa.Column("layout", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("borrador", "layout")
