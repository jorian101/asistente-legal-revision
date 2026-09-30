"""add estado column to consulta_historial

Revision ID: 0f1a2b3c4d5e
Revises: a9b8c7d6e5f4
Create Date: 2026-08-16 00:00:00.000000

Estado explicito del ciclo de vida de una consulta: 'en_progreso',
'completado' o 'error'. La Sala de Control deja de inferir el estado de
respuesta/tipo_respuesta NULL (bug: una consulta terminada que no persistio
la respuesta quedaba 'En progreso' para siempre).

Backfill conservador: las filas con respuesta+tipo presentes -> 'completado';
el resto (stuck por stream interrumpido o pipeline fallido) -> 'error'.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f1a2b3c4d5e"
down_revision: str | Sequence[str] | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Añade columna estado con backfill por estado real de la fila."""
    op.add_column(
        "consulta_historial",
        sa.Column(
            "estado",
            sa.String(length=16),
            server_default=sa.text("'en_progreso'"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE consulta_historial SET estado = 'completado' "
        "WHERE respuesta IS NOT NULL AND tipo_respuesta IS NOT NULL"
    )
    op.execute(
        "UPDATE consulta_historial SET estado = 'error' "
        "WHERE estado = 'en_progreso' AND (respuesta IS NULL OR tipo_respuesta IS NULL)"
    )


def downgrade() -> None:
    """Quita la columna estado."""
    op.drop_column("consulta_historial", "estado")
