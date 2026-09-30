"""ampliar borrador.estado: borrador/publicado/pendiente_oficial/oficial

Plan (ciclo obrado -> oficial): el operador solicita que un obrado pase a
oficial (publicado -> pendiente_oficial) y el supervisor aprueba
(pendiente_oficial -> oficial). Tambien el supervisor puede desoficializar
(oficial -> publicado o borrador) si se equivoco.

Revision ID: a9b8c7d6e5f4
Revises: f7a8b9c1d2e3
Create Date: 2026-08-16
"""

from __future__ import annotations

from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "f7a8b9c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("borrador_estado_check", "borrador", type_="check")
    op.create_check_constraint(
        "borrador_estado_check",
        "borrador",
        "estado IN ('borrador', 'publicado', 'pendiente_oficial', 'oficial')",
    )


def downgrade() -> None:
    op.drop_constraint("borrador_estado_check", "borrador", type_="check")
    op.create_check_constraint(
        "borrador_estado_check",
        "borrador",
        "estado IN ('borrador', 'publicado')",
    )
