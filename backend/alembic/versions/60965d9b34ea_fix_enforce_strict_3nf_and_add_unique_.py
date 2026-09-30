"""fix: enforce strict 3NF and add unique constraints

Revision ID: 60965d9b34ea
Revises: 8f345a460a82
Create Date: 2026-07-20 01:20:23.038535

Garantiza 3NF estricta en tablas de chat:
1. UNIQUE parcial en espacio_trabajo (expediente_id, propietario_id, nombre) WHERE estado='activo'
2. UNIQUE parcial en mensaje_chat (chat_id, posicion) WHERE estado IN ('activo','editado')
3. Trigger update_chat_last_message AFTER INSERT ON mensaje_chat
   mantiene chat_privado.ultimo_mensaje_at sincronizado (3NF: dato derivado
   se mantiene automaticamente, no se deja al adapter).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60965d9b34ea"
down_revision: str | Sequence[str] | None = "8f345a460a82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. UNIQUE parcial: espacio_trabajo (carpetas) - sin duplicados activos
    op.create_index(
        "espacio_trabajo_nombre_unico_activos",
        "espacio_trabajo",
        ["expediente_id", "propietario_id", "nombre"],
        unique=True,
        postgresql_where=sa.text("estado = 'activo'"),
    )

    # 2. UNIQUE parcial: mensaje_chat - sin colisiones de posicion para visibles
    op.create_index(
        "mensaje_chat_posicion_unico_visibles",
        "mensaje_chat",
        ["chat_id", "posicion"],
        unique=True,
        postgresql_where=sa.text("estado IN ('activo', 'editado')"),
    )

    # 3. Trigger update_chat_last_message: mantiene chat_privado.ultimo_mensaje_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_chat_last_message()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE chat_privado
            SET ultimo_mensaje_at = NEW.created_at
            WHERE id = NEW.chat_id
              AND (ultimo_mensaje_at IS NULL OR NEW.created_at > ultimo_mensaje_at);
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER update_chat_last_message_trigger
        AFTER INSERT ON mensaje_chat
        FOR EACH ROW EXECUTE FUNCTION update_chat_last_message()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS update_chat_last_message_trigger ON mensaje_chat")
    op.execute("DROP FUNCTION IF EXISTS update_chat_last_message()")
    op.drop_index(
        "mensaje_chat_posicion_unico_visibles",
        table_name="mensaje_chat",
        postgresql_where=sa.text("estado IN ('activo', 'editado')"),
    )
    op.drop_index(
        "espacio_trabajo_nombre_unico_activos",
        table_name="espacio_trabajo",
        postgresql_where=sa.text("estado = 'activo'"),
    )
