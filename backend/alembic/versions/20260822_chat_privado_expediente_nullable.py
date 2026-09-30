"""chat_privado.expediente_id nullable (chats generales)

Revision ID: b7c8d9e0f1a2
Revises: a0b1c2d3e4f5
Create Date: 2026-08-22 00:00:00.000000

Relaja chat_privado.expediente_id a NULL para permitir chats generales
(sin expediente) que se basan solo en el corpus de la base vectorial.
La entidad ya lo anticipaba en su docstring ("migracion Alembic aparte").

Downgrade: elimina los chats generales (expediente_id IS NULL) antes de
restaurar NOT NULL — un chat general no puede mapearse a un expediente.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permite chats sin expediente."""
    op.execute("ALTER TABLE chat_privado ALTER COLUMN expediente_id DROP NOT NULL")


def downgrade() -> None:
    """Restaura NOT NULL eliminando antes los chats generales."""
    op.execute("DELETE FROM chat_privado WHERE expediente_id IS NULL")
    op.execute("ALTER TABLE chat_privado ALTER COLUMN expediente_id SET NOT NULL")
