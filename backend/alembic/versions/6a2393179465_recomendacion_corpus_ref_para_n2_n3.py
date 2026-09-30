"""Recomendación de ítems de corpus N2/N3 (no solo obras globales).

- obra_global_id pasa a NULLABLE (recomendación por corpus no apunta a obra).
- corpus + corpus_ref NULLABLE (abreviatura norma: 'SCP-...', 'LIB-...').
- UNIQUE parcial (expediente, corpus, corpus_ref) cuando es por corpus.
  El UNIQUE original (obra_global_id, expediente_id) sigue valiendo para
  filas con obra (PG ignora NULLs en unique).

Revision ID: 6a2393179465
Revises: d8fa682ff556
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "6a2393179465"
down_revision: str | None = "d8fa682ff556"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "recomendacion_doctrina", "obra_global_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.add_column("recomendacion_doctrina", sa.Column("corpus", sa.String(), nullable=True))
    op.add_column("recomendacion_doctrina", sa.Column("corpus_ref", sa.String(), nullable=True))
    op.create_index(
        "uq_recomendacion_corpus_expediente",
        "recomendacion_doctrina",
        ["expediente_id", "corpus", "corpus_ref"],
        unique=True,
        postgresql_where=sa.text("obra_global_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_recomendacion_corpus_expediente", table_name="recomendacion_doctrina")
    op.drop_column("recomendacion_doctrina", "corpus_ref")
    op.drop_column("recomendacion_doctrina", "corpus")
    op.alter_column(
        "recomendacion_doctrina",
        "obra_global_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
