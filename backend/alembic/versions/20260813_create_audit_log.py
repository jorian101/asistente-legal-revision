"""create audit_log table

Revision ID: 6b1c2d3e4f5a
Revises: 5a1b2c3d4e5f
Create Date: 2026-08-13 00:00:00.000000

Tabla `audit_log` — Trail of Bits Regla R6 (trazabilidad de acciones
sensitivas). Append-only: registra accion/entidad/usuario/ip/created_at.
Indices compuestos para las queries del UC listar_auditoria:
  WHERE accion=? AND created_at>=?  (ix accion+created_at)
  WHERE usuario_id=?               (ix usuario_id)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6b1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "5a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea tabla audit_log."""
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("accion", sa.Text(), nullable=False),
        sa.Column("entidad", sa.Text(), nullable=True),
        sa.Column("entidad_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("detalle", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "audit_log_accion_created_at_idx",
        "audit_log",
        ["accion", "created_at"],
        unique=False,
    )
    op.create_index(
        "audit_log_usuario_idx",
        "audit_log",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tabla audit_log."""
    op.drop_index("audit_log_usuario_idx", table_name="audit_log")
    op.drop_index("audit_log_accion_created_at_idx", table_name="audit_log")
    op.drop_table("audit_log")
