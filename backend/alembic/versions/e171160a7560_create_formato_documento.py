"""create tabla formato_documento

Módulo formatos TSJM: formatos canónicos/crudos con bloques JSONB.

Revision ID: e171160a7560
Revises: f7a8b9c1d2e3
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "e171160a7560"
down_revision: str | None = "f7a8b9c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "formato_documento",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tipo_documento", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("autor", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False, server_default="borrador"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("meta", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("bloques", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("hash_fuente", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "tipo_documento IN ("
            "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
            "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
            "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
            "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro'"
            ")",
            name="formato_tipo_check",
        ),
        sa.CheckConstraint(
            "autor IN ('aliaga', 'tsjm-otro', 'instancia-inferior', 'parte', 'desconocido')",
            name="formato_autor_check",
        ),
        sa.CheckConstraint(
            "estado IN ('borrador', 'canonico')",
            name="formato_estado_check",
        ),
    )
    op.create_index("ix_formato_tipo", "formato_documento", ["tipo_documento"])
    op.create_index("ix_formato_autor", "formato_documento", ["autor"])
    op.create_index("ix_formato_estado", "formato_documento", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_formato_estado", table_name="formato_documento")
    op.drop_index("ix_formato_autor", table_name="formato_documento")
    op.drop_index("ix_formato_tipo", table_name="formato_documento")
    op.drop_table("formato_documento")
