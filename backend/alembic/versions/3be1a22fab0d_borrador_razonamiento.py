"""borrador_razonamiento — agrega columna razonamiento (modo pensar) a borrador.

Solo ADD COLUMN (additive, no destructiva). El autogenerate detecto drift
no relacionado (indices/constraints renombrados, tablas de otros modulos);
se recorto manualmente a esta columna. Revisado 2026-09-03.

Revision ID: 3be1a22fab0d
Revises: b4c5d6e7f8a9
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3be1a22fab0d"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega borrador.razonamiento (Text, default '')."""
    op.add_column(
        "borrador",
        sa.Column("razonamiento", sa.Text(), server_default=sa.text("''"), nullable=False),
    )


def downgrade() -> None:
    """Quita borrador.razonamiento."""
    op.drop_column("borrador", "razonamiento")
