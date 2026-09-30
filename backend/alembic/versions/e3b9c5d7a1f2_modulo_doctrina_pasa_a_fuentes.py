"""Modulo `doctrina`: pasa a llamarse Fuentes (normas, jurisprudencia y doctrina).

La pagina /asistente/doctrina gestiona ahora las tres categorias de fuentes con un
flujo comun. La clave y la ruta no cambian (los permisos por rol siguen valiendo);
solo el nombre y la descripcion visibles.

Revision ID: e3b9c5d7a1f2
Revises: d2a8b4c6e0f1
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision: str = "e3b9c5d7a1f2"
down_revision: str | None = "d2a8b4c6e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE modulo SET nombre = 'Fuentes', "
        "descripcion = 'Normas, jurisprudencia y doctrina' WHERE clave = 'doctrina'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE modulo SET nombre = 'Doctrina', "
        "descripcion = 'Doctrina global y aprobaciones' WHERE clave = 'doctrina'"
    )
