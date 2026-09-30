"""ampliar tipo_proceso con apelacion_restringida

Revision ID: 8c1d2e3f4a5b
Revises: 7b2c3d4e5f6a
Create Date: 2026-08-15 15:30:00.000000

El diccionario de variables del vault (casos reales) registra apelación
restringida además de incidental (casos 3187/3142). Se amplía el CHECK
constraint de la columna tipo_proceso de la tabla expediente.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c1d2e3f4a5b"
down_revision: str | Sequence[str] | None = "7b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUEVO_CHECK = "tipo_proceso IN ('consulta', 'apelacion_incidental', 'apelacion_restringida')"
CHECK_NOMBRE = "expediente_tipo_proceso_check"


def upgrade() -> None:
    """Reemplaza el CHECK constraint de tipo_proceso (no destructivo)."""
    op.drop_constraint(CHECK_NOMBRE, "expediente", type_="check")
    op.create_check_constraint(CHECK_NOMBRE, "expediente", NUEVO_CHECK)


def downgrade() -> None:
    """Restaura el CHECK original (sin apelacion_restringida)."""
    op.drop_constraint(CHECK_NOMBRE, "expediente", type_="check")
    op.create_check_constraint(
        CHECK_NOMBRE,
        "expediente",
        "tipo_proceso IN ('consulta', 'apelacion_incidental')",
    )
