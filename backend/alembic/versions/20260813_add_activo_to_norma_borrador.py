"""add activo column to norma and borrador

Revision ID: 8d1e2f3a4b5c
Revises: 7c1d2e3f4a5b
Create Date: 2026-08-13 02:00:00.000000

Soft delete universal (CRITICAL #3): columna `activo` en `norma` y
`borrador`. Los DELETE setean activo=False (Regla 7 para borrador:
filtro propietario) en vez de borrar fisicamente. El expediente ya tiene
`estado IN ('activo','archivado')` — su soft delete usa 'archivado'
(sin columna nueva, sin duplicar concepto). Indices parciales cubren los
listados activos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d1e2f3a4b5c"
down_revision: str | Sequence[str] | None = "7c1d2e3f4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Añade columna activo (default TRUE) a norma y borrador."""
    op.add_column(
        "norma",
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
    )
    op.add_column(
        "borrador",
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
    )
    op.execute("CREATE INDEX ix_norma_activo ON norma (abreviatura) WHERE activo = TRUE")
    op.execute("CREATE INDEX ix_borrador_activo ON borrador (expediente_id) WHERE activo = TRUE")


def downgrade() -> None:
    """Quita indices y columnas activo."""
    op.execute("DROP INDEX IF EXISTS ix_borrador_activo")
    op.execute("DROP INDEX IF EXISTS ix_norma_activo")
    op.drop_column("borrador", "activo")
    op.drop_column("norma", "activo")
