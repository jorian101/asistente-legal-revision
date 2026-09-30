"""vincular borrador con chat y mensaje que lo genero

Revision ID: a2b3c4d5e6f7
Revises: 9d1e2f3a4b5c
Create Date: 2026-08-15 17:30:00.000000

El borrador se genera dentro del chat de Consultar y se guarda explicitamente
desde ahi. Se agregan las FKs:
- borrador.chat_id -> chat_privado.id (ON DELETE SET NULL): chat donde se genero.
- borrador.mensaje_id -> mensaje_chat.id (ON DELETE SET NULL): mensaje bot origen.

Permite el boton 'Ver el chat' y 'Actualizar mi borrador' con continuidad real.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "9d1e2f3a4b5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega chat_id y mensaje_id a borrador."""
    op.add_column(
        "borrador",
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_privado.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "borrador",
        sa.Column(
            "mensaje_id",
            sa.BigInteger(),
            sa.ForeignKey("mensaje_chat.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("borrador_chat_idx", "borrador", ["chat_id"], unique=False)


def downgrade() -> None:
    """Elimina chat_id y mensaje_id de borrador."""
    op.drop_index("borrador_chat_idx", table_name="borrador")
    op.drop_column("borrador", "mensaje_id")
    op.drop_column("borrador", "chat_id")
