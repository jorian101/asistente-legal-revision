"""norma tipo doctrina_libro para N3 (libros académicos).

Agrega 'doctrina_libro' al CHECK norma_tipo_check (ficha N3,
niveles-corpus). Sin este valor, las filas N3 rebotan en DB.

Revision ID: 0dfb8ff2178a
Revises: 1928abeacf40
Create Date: 2026-09-16
"""

from __future__ import annotations

from alembic import op

revision: str = "0dfb8ff2178a"
down_revision: str | None = "1928abeacf40"
branch_labels = None
depends_on = None

_TIPOS = (
    "'constitucion', 'codigo_militar', 'codigo_ordinario', "
    "'ley_organica', 'reglamento', 'scp_tcp', 'sentencia_cidh', "
    "'doctrina_libro'"
)


def upgrade() -> None:
    op.drop_constraint("norma_tipo_check", "norma", type_="check")
    op.create_check_constraint("norma_tipo_check", "norma", f"tipo IN ({_TIPOS})")


def downgrade() -> None:
    op.drop_constraint("norma_tipo_check", "norma", type_="check")
    op.create_check_constraint(
        "norma_tipo_check",
        "norma",
        "tipo IN ("
        "'constitucion', 'codigo_militar', 'codigo_ordinario', "
        "'ley_organica', 'reglamento', 'scp_tcp', 'sentencia_cidh'"
        ")",
    )
