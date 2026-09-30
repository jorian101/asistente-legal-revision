"""agregar autor_instancia a obra

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-15 18:30:00.000000

Autor institucional de una obra (instancia inferior, ej. 'Tribunal
Permanente de Justicia Militar') para los archivos subidos al abrir el
expediente. Si es NULL, el autor es el usuario propietario (nombre + cargo).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega columna autor_instancia a obra."""
    op.add_column(
        "obra",
        sa.Column("autor_instancia", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Elimina la columna autor_instancia."""
    op.drop_column("obra", "autor_instancia")
