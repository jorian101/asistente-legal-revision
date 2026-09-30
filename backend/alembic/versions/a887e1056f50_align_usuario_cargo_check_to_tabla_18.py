"""align usuario.cargo check to tabla 18

Revision ID: a887e1056f50
Revises: 3f29ce1f4cba
Create Date: 2026-08-03 07:42:04.653792

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a887e1056f50"
down_revision: str | Sequence[str] | None = "3f29ce1f4cba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Alinea usuario.cargo CHECK a Tabla 18 de la tesis (elimina 5 incumbentes)."""
    # 1) Remapear cargos eliminados a 'Otro' ANTES del CHECK nuevo
    op.execute(
        "UPDATE usuario SET cargo = 'Otro' WHERE cargo IN "
        "('Vocal', 'Presidente', 'Secretaria', 'Vocal S.A.C.', 'Presidente de Sala')"
    )
    # 2) Drop CHECK viejo + crear CHECK nuevo (7 valores: Tabla 18 + Otro)
    op.drop_constraint("usuario_cargo_check", "usuario", type_="check")
    op.create_check_constraint(
        "usuario_cargo_check",
        "usuario",
        "cargo IN ('Auditor', 'Fiscal', 'Vocal Relator', 'Secretaria de Cámara', "
        "'Vocal Presidente', 'Auxiliar de Secretaría de Cámara', 'Otro')",
    )


def downgrade() -> None:
    """Downgrade: vuelve al CHECK Sprint 1 (7 valores originales)."""
    op.drop_constraint("usuario_cargo_check", "usuario", type_="check")
    op.create_check_constraint(
        "usuario_cargo_check",
        "usuario",
        "cargo IN ('Fiscal', 'Vocal', 'Presidente', 'Secretaria', "
        "'Vocal S.A.C.', 'Presidente de Sala', 'Otro')",
    )
