"""add activo column to consulta_historial

Revision ID: 7c1d2e3f4a5b
Revises: 6b1c2d3e4f5a
Create Date: 2026-08-13 01:00:00.000000

Soft delete universal (CRITICAL #3/#4): columna `activo` en
consulta_historial. Los DELETE de historial setean activo=False (Regla 4:
solo el propietario) en vez de borrar fisicamente. Index parcial cubre las
queries de listado activo (WHERE activo = TRUE).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1d2e3f4a5b"
down_revision: str | Sequence[str] | None = "6b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Añade columna activo (default TRUE) + indice parcial."""
    op.add_column(
        "consulta_historial",
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
    )
    # Index parcial: solo filas activas en las queries de listado.
    op.execute(
        "CREATE INDEX ix_consulta_historial_activo "
        "ON consulta_historial (usuario_id, created_at DESC) "
        "WHERE activo = TRUE"
    )


def downgrade() -> None:
    """Quita indice y columna activo."""
    op.execute("DROP INDEX IF EXISTS ix_consulta_historial_activo")
    op.drop_column("consulta_historial", "activo")
