"""sprint_6_add_temperatura_config

Agrega 1 columna a la tabla singleton `configuracion_rag` para controlar
la temperatura del LLM en Sprint 6:

- temperatura: FLOAT NOT NULL DEFAULT 0.1 (rigurosidad legal maxima)

Revision ID: 9b3c5e1f8a01
Revises: 7e8a9f4b2c1d
Create Date: 2026-08-09
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3c5e1f8a01"
down_revision: str = "7e8a9f4b2c1d"
branch_labels: str = None
depends_on: str = None


def upgrade() -> None:
    op.add_column(
        "configuracion_rag",
        sa.Column(
            "temperatura",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("configuracion_rag", "temperatura")
