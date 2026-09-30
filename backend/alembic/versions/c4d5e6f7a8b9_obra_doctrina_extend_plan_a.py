"""obra doctrina extend (Plan A): expediente nullable + estados + criterio + soft delete

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-15 16:00:00.000000

Plan A (conectar vault a Valnor):
- obra.expediente_id -> nullable (doctrina global sin expediente).
- estado_visibilidad CHECK -> 4 estados (privado/publicado/global/rechazado).
- tipo_documento CHECK -> + 'criterio'.
- campos de doctrina: autor, fecha_documento, procedencia, estado_validacion,
  motivo_rechazo, recomendada.
- soft delete: activo BOOLEAN DEFAULT TRUE.
- tabla nueva obra_origen (trazabilidad de doctrina global copiada a expediente).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. expediente_id nullable (doctrina global sin expediente).
    op.alter_column("obra", "expediente_id", existing_type=sa.BigInteger(), nullable=True)

    # 2. Nuevos campos de doctrina + soft delete.
    op.add_column("obra", sa.Column("autor", sa.String(), nullable=True))
    op.add_column("obra", sa.Column("fecha_documento", sa.String(), nullable=True))
    op.add_column("obra", sa.Column("procedencia", sa.String(), nullable=True))
    op.add_column("obra", sa.Column("estado_validacion", sa.String(), nullable=True))
    op.add_column("obra", sa.Column("motivo_rechazo", sa.String(), nullable=True))
    op.add_column(
        "obra",
        sa.Column("recomendada", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )
    op.add_column(
        "obra", sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"))
    )

    # 3. Ampliar CHECKs (drop + recreate con nombre fijo).
    op.drop_constraint("obra_estado_visibilidad_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_estado_visibilidad_check",
        "obra",
        "estado_visibilidad IN ('privado', 'publicado', 'global', 'rechazado')",
    )
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_tipo_documento_check",
        "obra",
        "tipo_documento IN ("
        "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
        "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
        "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
        "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'criterio', 'otro'"
        ")",
    )

    # 4. Tabla nueva obra_origen (trazabilidad doctrina global -> expediente).
    op.create_table(
        "obra_origen",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "obra_id", sa.BigInteger(), sa.ForeignKey("obra.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "obra_origen_id",
            sa.BigInteger(),
            sa.ForeignKey("obra.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("copiada_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column(
            "copiada_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sin_expediente", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("obra_origen")
    op.drop_constraint("obra_tipo_documento_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_tipo_documento_check",
        "obra",
        "tipo_documento IN ("
        "'sentencia', 'memorial_apelacion', 'auto_interlocutorio', "
        "'oficio_elevacion', 'acta_audiencia', 'requerimiento_fiscal', "
        "'dictamen_radicatoria', 'dictamen_fondo', 'relacion_obrados', "
        "'proyecto_auto_vista', 'auto_vista', 'doctrina', 'otro'"
        ")",
    )
    op.drop_constraint("obra_estado_visibilidad_check", "obra", type_="check")
    op.create_check_constraint(
        "obra_estado_visibilidad_check",
        "obra",
        "estado_visibilidad IN ('privado', 'publicado')",
    )
    op.drop_column("obra", "activo")
    op.drop_column("obra", "recomendada")
    op.drop_column("obra", "motivo_rechazo")
    op.drop_column("obra", "estado_validacion")
    op.drop_column("obra", "procedencia")
    op.drop_column("obra", "fecha_documento")
    op.drop_column("obra", "autor")
    op.alter_column("obra", "expediente_id", existing_type=sa.BigInteger(), nullable=False)
