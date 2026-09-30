"""Obra: índices para punteros de corpus N2/N3.

- obra_corpus_ref_idx parcial (corpus_ref IS NOT NULL): resolución de
  punteros en PipelineRAG (obtener_por_ids) y listados por referencia.
- obra_corpus_idx parcial (corpus IS NOT NULL): listados por corpus.

Migración separada de la de columnas por auditoría (pedido vocal).

Revision ID: f3cee9beab90
Revises: 6a2393179465
Create Date: 2026-09-17
"""

from __future__ import annotations

from alembic import op

revision: str = "f3cee9beab90"
down_revision: str | None = "6a2393179465"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "obra_corpus_ref_idx",
        "obra",
        ["corpus_ref"],
        postgresql_where="corpus_ref IS NOT NULL",
    )
    op.create_index(
        "obra_corpus_idx",
        "obra",
        ["corpus"],
        postgresql_where="corpus IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("obra_corpus_idx", table_name="obra")
    op.drop_index("obra_corpus_ref_idx", table_name="obra")
