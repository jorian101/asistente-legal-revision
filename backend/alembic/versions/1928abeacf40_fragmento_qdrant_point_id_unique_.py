"""fragmento qdrant_point_id: UNIQUE total -> parcial (solo indexados).

Los nodos estructurales (D-S2C-06) persisten en PG con qdrant_point_id=''
como marca de "no indexable" (Fragmento.es_indexable). Con UNIQUE total,
la segunda fila estructural revienta (UniqueViolation). El índice parcial
permite múltiples '' y sigue garantizando unicidad de puntos reales.

Revision ID: 1928abeacf40
Revises: f9e8d7c6b5a4
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "1928abeacf40"
down_revision: str | None = "f9e8d7c6b5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_fragmento_qdrant_point_id", "fragmento", type_="unique")
    op.create_index(
        "uq_fragmento_qdrant_point_id",
        "fragmento",
        ["qdrant_point_id"],
        unique=True,
        postgresql_where=sa.text("qdrant_point_id <> ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_fragmento_qdrant_point_id", table_name="fragmento")
    op.create_unique_constraint("uq_fragmento_qdrant_point_id", "fragmento", ["qdrant_point_id"])
