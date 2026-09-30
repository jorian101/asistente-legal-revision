"""crear tablas norma y fragmento (Sprint 0 — Corpus Indexing)

Revision ID: a1c7d2e9f034
Revises: 8f345a460a82
Create Date: 2026-07-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c7d2e9f034"
# Merge explicito: mi migracion depende de AMBOS heads actuales del arbol
# (8f345a460a82 fue la ultima aplicada; 60965d9b34ea es una migracion 3NF
# estricta pendiente del Sprint anterior pero independiente de mi esquema).
down_revision: str | Sequence[str] | None = (
    "8f345a460a82",
    "60965d9b34ea",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crear tablas `norma` y `fragmento` segun arquitectura.md seccion 3.1."""
    # ----------------------------------------------------------------------
    # Tabla `norma`
    # ----------------------------------------------------------------------
    op.create_table(
        "norma",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("abreviatura", sa.String(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("jerarquia", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("ruta_archivo", sa.String(), nullable=True),
        sa.Column(
            "indexado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("indexado_por", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo IN ("
            "'constitucion', 'codigo_militar', 'codigo_ordinario', "
            "'ley_organica', 'reglamento', 'scp_tcp', 'sentencia_cidh'"
            ")",
            name="norma_tipo_check",
        ),
        sa.CheckConstraint(
            "jerarquia IN ('suprema', 'militar', 'supletoria', 'jurisprudencia', 'doctrina')",
            name="norma_jerarquia_check",
        ),
        sa.ForeignKeyConstraint(["indexado_por"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("abreviatura", name="uq_norma_abreviatura"),
    )
    op.create_index(op.f("ix_norma_abreviatura"), "norma", ["abreviatura"], unique=False)
    op.create_index("norma_indexado_idx", "norma", ["indexado"], unique=False)
    op.create_index("norma_tipo_jerarquia_idx", "norma", ["tipo", "jerarquia"], unique=False)
    op.create_index(op.f("ix_norma_indexado_por"), "norma", ["indexado_por"], unique=False)

    # ----------------------------------------------------------------------
    # Tabla `fragmento`
    # ----------------------------------------------------------------------
    op.create_table(
        "fragmento",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("norma_id", sa.BigInteger(), nullable=True),
        sa.Column("obra_id", sa.BigInteger(), nullable=True),
        sa.Column("expediente_id", sa.BigInteger(), nullable=True),
        sa.Column("qdrant_point_id", sa.String(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("padre_ref_id", sa.BigInteger(), nullable=True),
        sa.Column("padre_ref_key", sa.String(), nullable=True),
        sa.Column("nivel_jerarquico", sa.Integer(), nullable=True),
        sa.Column("metadatos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "(norma_id IS NOT NULL) OR (obra_id IS NOT NULL)",
            name="fragmento_norma_or_obra_check",
        ),
        sa.CheckConstraint(
            "(nivel_jerarquico IS NULL) OR (nivel_jerarquico BETWEEN 0 AND 4)",
            name="fragmento_nivel_jerarquico_check",
        ),
        sa.ForeignKeyConstraint(["norma_id"], ["norma.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obra_id"], ["obra.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expediente_id"], ["expediente.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["padre_ref_id"], ["fragmento.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qdrant_point_id", name="uq_fragmento_qdrant_point_id"),
    )
    op.create_index(
        op.f("ix_fragmento_qdrant_point_id"),
        "fragmento",
        ["qdrant_point_id"],
        unique=False,
    )
    op.create_index(op.f("ix_fragmento_norma_id"), "fragmento", ["norma_id"], unique=False)
    op.create_index(op.f("ix_fragmento_obra_id"), "fragmento", ["obra_id"], unique=False)
    op.create_index(
        op.f("ix_fragmento_expediente_id"),
        "fragmento",
        ["expediente_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fragmento_padre_ref_id"),
        "fragmento",
        ["padre_ref_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tablas en orden inverso por la FK de self-ref en `fragmento`."""
    op.drop_index(op.f("ix_fragmento_padre_ref_id"), table_name="fragmento")
    op.drop_index(op.f("ix_fragmento_expediente_id"), table_name="fragmento")
    op.drop_index(op.f("ix_fragmento_obra_id"), table_name="fragmento")
    op.drop_index(op.f("ix_fragmento_norma_id"), table_name="fragmento")
    op.drop_index(op.f("ix_fragmento_qdrant_point_id"), table_name="fragmento")
    op.drop_table("fragmento")

    op.drop_index(op.f("ix_norma_indexado_por"), table_name="norma")
    op.drop_index("norma_tipo_jerarquia_idx", table_name="norma")
    op.drop_index("norma_indexado_idx", table_name="norma")
    op.drop_index(op.f("ix_norma_abreviatura"), table_name="norma")
    op.drop_table("norma")
