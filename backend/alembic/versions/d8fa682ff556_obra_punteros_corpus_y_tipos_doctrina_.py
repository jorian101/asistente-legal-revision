"""Obra como puntero a corpus N2/N3 + nuevos tipos de documento.

- tipo_documento: agrega 'doctrina_libro', 'jurisprudencia', 'ejemplo',
  'material_caso'. 'doctrina' legacy se conserva (alias deprecado).
- columnas corpus (jurisprudencia|doctrina, NULL = pieza propia) y
  corpus_ref (abreviatura norma: 'SCP-0623-2024-S4', 'LIB-...'), NULL
  por defecto. El puntero no duplica contenido (contenido_texto='').

Revision ID: d8fa682ff556
Revises: 0dfb8ff2178a
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "d8fa682ff556"
down_revision: str | None = "0dfb8ff2178a"
branch_labels = None
depends_on = None

_TIPOS = (
    "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
    "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
    "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
    "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro', "
    "'doctrina_libro', 'jurisprudencia', 'ejemplo', 'material_caso'"
)

_TIPOS_VIEJOS = (
    "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
    "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
    "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
    "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro'"
)


def upgrade() -> None:
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint("obra_tipo_documento_check", "obra", f"tipo_documento IN ({_TIPOS})")
    op.add_column("obra", sa.Column("corpus", sa.String(), nullable=True))
    op.add_column("obra", sa.Column("corpus_ref", sa.String(), nullable=True))
    op.create_check_constraint(
        "obra_corpus_check",
        "obra",
        "corpus IS NULL OR corpus IN ('jurisprudencia', 'doctrina')",
    )


def downgrade() -> None:
    op.drop_constraint("obra_corpus_check", "obra", type_="check")
    op.drop_column("obra", "corpus_ref")
    op.drop_column("obra", "corpus")
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_tipo_documento_check",
        "obra",
        f"tipo_documento IN ({_TIPOS_VIEJOS})",
    )
