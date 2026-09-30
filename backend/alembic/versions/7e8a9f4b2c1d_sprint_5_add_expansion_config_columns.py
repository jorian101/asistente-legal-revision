"""sprint_5_add_expansion_config_columns

Agrega 2 columnas a la tabla singleton `configuracion_rag` para controlar
el ExpansorJerarquico (Sprint 5):

- max_profundidad_bfs: profundidad máxima del CTE recursivo ascendente (default 3)
- top_k_padres_a_incluir: límite de nodos padre a inyectar en ContextoExpandido (default 5)

Revision ID: 7e8a9f4b2c1d
Revises: 222f48d718c2
Create Date: 2026-08-08
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e8a9f4b2c1d"
down_revision: str = "222f48d718c2"
branch_labels: str = None
depends_on: str = None


def upgrade() -> None:
    # max_profundidad_bfs: INTEGER NOT NULL DEFAULT 3
    op.add_column(
        "configuracion_rag",
        sa.Column(
            "max_profundidad_bfs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
    )
    # top_k_padres_a_incluir: INTEGER NOT NULL DEFAULT 5
    op.add_column(
        "configuracion_rag",
        sa.Column(
            "top_k_padres_a_incluir",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )


def downgrade() -> None:
    op.drop_column("configuracion_rag", "max_profundidad_bfs")
    op.drop_column("configuracion_rag", "top_k_padres_a_incluir")
