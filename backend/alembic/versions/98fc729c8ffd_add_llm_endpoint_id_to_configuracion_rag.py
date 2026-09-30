"""add llm_endpoint_id to configuracion_rag

Revision ID: 98fc729c8ffd
Revises: 8d1e2f3a4b5c
Create Date: 2026-08-13 16:38:09.458002

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "98fc729c8ffd"
down_revision: str | Sequence[str] | None = "8d1e2f3a4b5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("configuracion_rag", sa.Column("llm_endpoint_id", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("configuracion_rag", "llm_endpoint_id")
