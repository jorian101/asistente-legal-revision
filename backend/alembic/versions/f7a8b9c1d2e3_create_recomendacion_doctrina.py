"""create tabla recomendacion_doctrina

Plan (recomendacion de doctrina por expediente): permite a supervisores y
operadores marcar una doctrina GLOBAL como recomendada para un expediente
especifico. Supervisor auto-aprueba su recomendacion; operador propone y el
supervisor aprueba. UNIQUE(obra_global_id, expediente_id) = una recomendacion
por par.

Revision ID: f7a8b9c1d2e3
Revises: e6f7a8b9c1d2
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c1d2e3"
down_revision: str | None = "e6f7a8b9c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recomendacion_doctrina",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "obra_global_id",
            sa.BigInteger(),
            sa.ForeignKey("obra.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "expediente_id",
            sa.BigInteger(),
            sa.ForeignKey("expediente.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recomendado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.String(),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column(
            "aprobado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("motivo_rechazo", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "obra_global_id", "expediente_id", name="uq_recomendacion_obra_expediente"
        ),
    )
    op.create_index(
        "ix_recomendacion_expediente",
        "recomendacion_doctrina",
        ["expediente_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recomendacion_expediente", table_name="recomendacion_doctrina")
    op.drop_table("recomendacion_doctrina")
