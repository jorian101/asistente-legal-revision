"""Fuentes: trazabilidad de la promoción de obrados y fragmento exclusivo.

- norma.origen_obra_id: obra desde la que se promovió una norma (jurisprudencia o
  norma promovida desde un obrado). NULL para el corpus cargado por el admin.
  ON DELETE SET NULL: borrar la obra no debe borrar la norma.
- fragmento_norma_or_obra_check pasa de OR a exclusivo (num_nonnulls = 1): un
  fragmento es de una norma O de una obra, nunca de ambas. Verificado antes de
  escribir esta revisión: 0 filas violan el nuevo CHECK.

Revision ID: a7c3e9d1f2b4
Revises: f3cee9beab90
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "a7c3e9d1f2b4"
down_revision: str | None = "f3cee9beab90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "norma",
        sa.Column(
            "origen_obra_id",
            sa.BigInteger(),
            sa.ForeignKey("obra.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "norma_origen_obra_idx",
        "norma",
        ["origen_obra_id"],
        postgresql_where=sa.text("origen_obra_id IS NOT NULL"),
    )
    op.drop_constraint("fragmento_norma_or_obra_check", "fragmento", type_="check")
    op.create_check_constraint(
        "fragmento_norma_or_obra_check",
        "fragmento",
        "num_nonnulls(norma_id, obra_id) = 1",
    )


def downgrade() -> None:
    op.drop_constraint("fragmento_norma_or_obra_check", "fragmento", type_="check")
    op.create_check_constraint(
        "fragmento_norma_or_obra_check",
        "fragmento",
        "(norma_id IS NOT NULL) OR (obra_id IS NOT NULL)",
    )
    op.drop_index("norma_origen_obra_idx", table_name="norma")
    op.drop_column("norma", "origen_obra_id")
