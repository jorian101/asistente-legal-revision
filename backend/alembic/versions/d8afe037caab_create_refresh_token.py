"""create refresh_token table

Revision ID: d8afe037caab
Revises: 3be43b48654a
Create Date: 2026-08-02 22:30:30.000000

Tabla `refresh_token` para soportar Regla 2 Trail of Bits:
- rotacion de refresh tokens (cada uso invalida el anterior)
- deteccion de replay -> revocacion total del usuario
- expiracion 7 dias

Almacenamos SHA-256 del token opaco (nunca el raw) para que un leak de BD
no permita suplantacion. El token raw solo vive en la cookie httpOnly del
cliente.

Sprint 1 Auth, Migracion M2 del plan v3.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8afe037caab"
down_revision: str | Sequence[str] | None = "3be43b48654a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea tabla refresh_token."""
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indice para buscar tokens por usuario (rotacion, revocacion total).
    op.create_index("ix_refresh_token_usuario_id", "refresh_token", ["usuario_id"], unique=False)
    # Indice unico para lookup por hash (verificacion + deteccion replay).
    op.create_index("ix_refresh_token_token_hash", "refresh_token", ["token_hash"], unique=True)


def downgrade() -> None:
    """Drop tabla refresh_token."""
    op.drop_index("ix_refresh_token_token_hash", table_name="refresh_token")
    op.drop_index("ix_refresh_token_usuario_id", table_name="refresh_token")
    op.drop_table("refresh_token")
