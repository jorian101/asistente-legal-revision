"""add normalizar_query to configuracion_rag

Agrega 1 columna a la tabla singleton `configuracion_rag` para activar o
desactivar la normalizacion de la query del usuario antes del embedding
(Capa A, bug sala):

- normalizar_query: BOOLEAN NOT NULL DEFAULT true (limpiar saludos,
  muletillas y typos por edit-distance contra el vocabulario del corpus).

True por default; desactivable por admin via
PUT /admin/corpus/configuracion-rag/normalizar-query.

Revision ID: 4f2a8c6d3e10
Revises: 3b9615747950
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2a8c6d3e10"
down_revision: str | Sequence[str] | None = "3b9615747950"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "configuracion_rag",
        sa.Column("normalizar_query", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("configuracion_rag", "normalizar_query")
