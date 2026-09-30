"""add columna esqueleto a formato_documento

Almacena el formato con marca de plantilla (template/texto_plantilla) y
placeholders {{VAR}}, derivado de formato.json. Alimenta la vista documento-like
y el export Word/PDF del asistente.

Revision ID: 57330097db35
Revises: 1d3b16ca6350
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "57330097db35"
down_revision: str | None = "1d3b16ca6350"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "formato_documento",
        sa.Column("esqueleto", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("formato_documento", "esqueleto")
