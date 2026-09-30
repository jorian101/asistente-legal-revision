"""crear tablas configuracion_rag y consulta_historial

Revision ID: 222f48d718c2
Revises: a887e1056f50
Create Date: 2026-08-04 09:18:46.758589

Decisiones de diseño (D11 — sesion plan Sprint 3):
- consulta_historial.expediente_id es NULL: una consulta_simple no requiere
  expediente (solo auto_vista_* lo requieren, validado en use case).
- consulta_historial.respuesta es NULL en Sprint 3: la respuesta LLM llega
  en Sprint 6; Sprint 3 persiste el ContextoRecuperado en fuentes_recuperadas.
- consulta_historial.tipo_respuesta extra (D11): consulta_simple |
  auto_vista_consulta | auto_vista_apelacion_incidental.
- configuracion_rag es singleton: se inserta la fila inicial en upgrade().
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "222f48d718c2"
down_revision: str | Sequence[str] | None = "a887e1056f50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crear tablas `configuracion_rag` y `consulta_historial` (arquitectura.md
    seccion 3.1) + fila inicial singleton de configuracion_rag."""
    op.create_table(
        "configuracion_rag",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "score_threshold",
            sa.Numeric(precision=3, scale=2),
            server_default=sa.text("0.75"),
            nullable=False,
        ),
        sa.Column("top_k_denso", sa.Integer(), server_default=sa.text("40"), nullable=False),
        sa.Column("top_k_lexico", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("top_k_final", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column(
            "modelo_embeddings",
            sa.String(),
            server_default=sa.text("'nomic-embed-text'"),
            nullable=False,
        ),
        sa.Column(
            "modelo_llm_default", sa.String(), server_default=sa.text("'llama3:8b'"), nullable=False
        ),
        sa.Column("actualizado_por", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "consulta_historial",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("expediente_id", sa.BigInteger(), nullable=True),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("respuesta", sa.Text(), nullable=True),
        sa.Column("tipo_respuesta", sa.String(), nullable=True),
        sa.Column("fuentes_recuperadas", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latencia_ms", sa.Integer(), nullable=True),
        sa.Column("modelo_llm", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "consulta_historial_created_at_idx", "consulta_historial", ["created_at"], unique=False
    )
    op.create_index(
        "consulta_historial_expediente_usuario_idx",
        "consulta_historial",
        ["expediente_id", "usuario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_consulta_historial_usuario_id"), "consulta_historial", ["usuario_id"], unique=False
    )

    # Singleton: una sola fila activa (arquitectura.md:276). Solo el
    # Administrador la modifica (HU-23), siempre via UPDATE, nunca INSERT.
    op.execute(
        "INSERT INTO configuracion_rag "
        "(score_threshold, top_k_denso, top_k_lexico, top_k_final) "
        "VALUES (0.75, 40, 20, 7)"
    )


def downgrade() -> None:
    """Drop de ambas tablas (la FK de consulta_historial cae por CASCADE)."""
    op.drop_index(op.f("ix_consulta_historial_usuario_id"), table_name="consulta_historial")
    op.drop_index("consulta_historial_expediente_usuario_idx", table_name="consulta_historial")
    op.drop_index("consulta_historial_created_at_idx", table_name="consulta_historial")
    op.drop_table("consulta_historial")
    op.drop_table("configuracion_rag")
