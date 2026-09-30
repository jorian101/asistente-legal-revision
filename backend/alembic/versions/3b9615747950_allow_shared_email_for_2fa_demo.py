"""allow shared email for 2fa demo

Revision ID: 3b9615747950
Revises: 98fc729c8ffd
Create Date: 2026-08-13 21:28:00.735788

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9615747950"
down_revision: str | Sequence[str] | None = "98fc729c8ffd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Quita UNIQUE en email para permitir que varios usuarios usen el mismo
    correo (demo 2FA: 10702171/81/91 comparten jaliagam1@est.emi.edu.bo)."""
    # IF EXISTS: ninguna migracion anterior crea `ix_usuario_email` (solo la UNIQUE
    # `usuario_email_key`); una BD nueva fallaba aqui. Las BD ya migradas no cambian.
    op.execute("ALTER TABLE usuario DROP CONSTRAINT IF EXISTS usuario_email_key")
    op.execute("DROP INDEX IF EXISTS ix_usuario_email")
    op.create_index("ix_usuario_email", "usuario", ["email"], unique=False)


def downgrade() -> None:
    """Restaura UNIQUE en email."""
    op.drop_index("ix_usuario_email", table_name="usuario")
    op.create_index("ix_usuario_email", "usuario", ["email"], unique=True)
    op.create_unique_constraint("usuario_email_key", "usuario", ["email"])
