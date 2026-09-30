"""agregar modulo formatos al catalogo (pipeline alta fidelidad TSJM)

Revision ID: 1d3b16ca6350
Revises: c9d0e1f2a3b4, e171160a7560 (merge)
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1d3b16ca6350"
down_revision: str | Sequence[str] | None = ("c9d0e1f2a3b4", "e171160a7560")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO modulo (clave, nombre, descripcion, ruta, orden) "
            "VALUES (:clave, :nombre, :descripcion, :ruta, :orden) "
            "ON CONFLICT (clave) DO NOTHING"
        ).bindparams(
            clave="formatos",
            nombre="Formatos TSJM",
            descripcion="Layouts de obrados TSJM",
            ruta="/admin/formatos",
            orden=16,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM modulo WHERE clave = :clave").bindparams(clave="formatos"))
