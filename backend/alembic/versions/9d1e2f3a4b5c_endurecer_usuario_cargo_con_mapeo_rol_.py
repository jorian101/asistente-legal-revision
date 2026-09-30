"""endurecer usuario.cargo con mapeo rol-cargo Tabla 18

Revision ID: 9d1e2f3a4b5c
Revises: 8c1d2e3f4a5b
Create Date: 2026-08-15 16:30:00.000000

Alinea usuario.cargo a la Tabla 18 del marco-practico: cada rol solo admite
los cargos de la SAC que le corresponden (sin 'Otro', que era el escape
legacy). El administrador pasa a 'Personal Técnico' (no pertenece a la SAC).

Corrección de datos previa al CHECK estricto:
- administrador con cargo 'Otro' -> 'Personal Técnico'
- supervisor con cargo 'Otro' -> 'Vocal Presidente' (seed histórico
  'Presidente de Sala', inexistente en Tabla 18; Vocal Presidente es el cargo
  de mayor jerarquía del supervisor en la SAC)
- operador_juridico con cargo 'Vocal Presidente' -> se reasigna el ROL a
  'supervisor' (el cargo es de supervisor; el cargo manda sobre el rol)
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d1e2f3a4b5c"
down_revision: str | Sequence[str] | None = "8c1d2e3f4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CARGO_CHECK_NOMBRE = "usuario_cargo_check"

NUEVO_CHECK = (
    "cargo IN ('Auditor', 'Fiscal', 'Vocal Relator', 'Secretaria de Cámara', "
    "'Vocal Presidente', 'Auxiliar de Secretaría de Cámara', 'Personal Técnico')"
)


def upgrade() -> None:
    """Corrige datos y reemplaza el CHECK de cargo (sin 'Otro')."""
    # 0) Drop del CHECK viejo ANTES de tocar datos (evita violaciones).
    op.drop_constraint(CARGO_CHECK_NOMBRE, "usuario", type_="check")

    # 1) Admin con 'Otro' -> Personal Técnico.
    op.execute(
        "UPDATE usuario SET cargo = 'Personal Técnico' "
        "WHERE rol = 'administrador' AND cargo = 'Otro'"
    )
    # 2) Supervisor con 'Otro' -> Vocal Presidente (seed histórico).
    op.execute(
        "UPDATE usuario SET cargo = 'Vocal Presidente' WHERE rol = 'supervisor' AND cargo = 'Otro'"
    )
    # 3) Operador con 'Vocal Presidente' -> reasignar rol a supervisor
    #    (el cargo es de supervisor; el cargo manda sobre el rol).
    op.execute(
        "UPDATE usuario SET rol = 'supervisor' "
        "WHERE rol = 'operador_juridico' AND cargo = 'Vocal Presidente'"
    )

    # 4) Crear CHECK estricto (sin 'Otro').
    op.create_check_constraint(CARGO_CHECK_NOMBRE, "usuario", NUEVO_CHECK)


def downgrade() -> None:
    """Restaura el CHECK anterior (con 'Otro'). No revierte datos."""
    op.drop_constraint(CARGO_CHECK_NOMBRE, "usuario", type_="check")
    op.create_check_constraint(
        CARGO_CHECK_NOMBRE,
        "usuario",
        "cargo IN ('Auditor', 'Fiscal', 'Vocal Relator', 'Secretaria de Cámara', "
        "'Vocal Presidente', 'Auxiliar de Secretaría de Cámara', 'Otro')",
    )
