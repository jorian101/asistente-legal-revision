"""Norma: propietario y estado de visibilidad (privada -> global con aprobacion).

Normas, jurisprudencia y libros comparten el flujo de las obras de doctrina:
el operador sube una fuente privada, la propone (`pendiente`) y el supervisor la
aprueba (`global`) o la rechaza con motivo. El corpus existente queda `global` y
sin propietario. Los puntos de Qdrant de una fuente privada llevan `visibilidad`
y `propietario_id` (el filtro de privacidad los respeta).

Revision ID: c9e5a1b3d7f2
Revises: a7c3e9d1f2b4
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "c9e5a1b3d7f2"
down_revision: str | None = "a7c3e9d1f2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "norma",
        sa.Column(
            "propietario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "norma",
        sa.Column("estado_visibilidad", sa.String(), nullable=False, server_default="global"),
    )
    op.add_column("norma", sa.Column("motivo_rechazo", sa.String(), nullable=True))
    op.create_check_constraint(
        "norma_estado_visibilidad_check",
        "norma",
        "estado_visibilidad IN ('privado', 'pendiente', 'global', 'rechazado')",
    )
    op.create_index("ix_norma_propietario_id", "norma", ["propietario_id"])
    op.create_index("ix_norma_estado_visibilidad", "norma", ["estado_visibilidad"])


def downgrade() -> None:
    op.drop_index("ix_norma_estado_visibilidad", table_name="norma")
    op.drop_index("ix_norma_propietario_id", table_name="norma")
    op.drop_constraint("norma_estado_visibilidad_check", "norma", type_="check")
    op.drop_column("norma", "motivo_rechazo")
    op.drop_column("norma", "estado_visibilidad")
    op.drop_column("norma", "propietario_id")
