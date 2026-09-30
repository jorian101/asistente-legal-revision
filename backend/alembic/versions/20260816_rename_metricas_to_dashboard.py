"""rename metricas module to Dashboard and reorder below Inicio

Revision ID: a0b1c2d3e4f5
Revises: 0f1a2b3c4d5e
Create Date: 2026-08-16 00:00:00.000000

El modulo 'metricas' pasa a llamarse 'Dashboard' (resumen general de chats y
modelos) y se ubica primero en el sidebar del admin (orden 1, debajo de
'Inicio' que es fijo). Usuarios y Corpus corren una posicion.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: str | Sequence[str] | None = "0f1a2b3c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Renombra metricas a Dashboard y lo ubica primero (orden 1)."""
    op.execute(
        sa.text(
            "UPDATE modulo SET nombre = 'Dashboard', "
            "descripcion = 'Resumen general de chats y modelos', orden = 1 "
            "WHERE clave = 'metricas'"
        )
    )
    op.execute(sa.text("UPDATE modulo SET orden = orden + 1 WHERE clave IN ('usuarios', 'corpus')"))


def downgrade() -> None:
    """Reverte el renombrado y reorden."""
    op.execute(
        sa.text(
            "UPDATE modulo SET nombre = 'Métricas', "
            "descripcion = 'Monitoreo del RAG, latencia y uso', orden = 3 "
            "WHERE clave = 'metricas'"
        )
    )
    op.execute(sa.text("UPDATE modulo SET orden = orden - 1 WHERE clave IN ('usuarios', 'corpus')"))
