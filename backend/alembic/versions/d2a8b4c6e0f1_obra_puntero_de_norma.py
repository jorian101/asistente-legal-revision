"""Obra: puntero a una norma del corpus (corpus 'norma', tipo 'norma_corpus').

Las normas tambien se pueden fijar en el chat como jurisprudencia y doctrina
(aunque el corpus juridico siempre esta en la busqueda: fijarla la prioriza).

Revision ID: d2a8b4c6e0f1
Revises: c9e5a1b3d7f2
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision: str = "d2a8b4c6e0f1"
down_revision: str | None = "c9e5a1b3d7f2"
branch_labels = None
depends_on = None

_TIPOS_ANTES = (
    "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
    "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
    "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
    "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro', "
    "'doctrina_libro', 'jurisprudencia', 'ejemplo', 'material_caso'"
)


def upgrade() -> None:
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_tipo_documento_check", "obra", f"tipo_documento IN ({_TIPOS_ANTES}, 'norma_corpus')"
    )
    op.drop_constraint("obra_corpus_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_corpus_check",
        "obra",
        "corpus IS NULL OR corpus IN ('jurisprudencia', 'doctrina', 'norma')",
    )


def downgrade() -> None:
    # Falla si existen punteros de norma (a proposito: no se pierden datos).
    op.drop_constraint("obra_corpus_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_corpus_check", "obra", "corpus IS NULL OR corpus IN ('jurisprudencia', 'doctrina')"
    )
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_tipo_documento_check", "obra", f"tipo_documento IN ({_TIPOS_ANTES})"
    )
