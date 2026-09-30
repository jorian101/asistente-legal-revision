"""fix ruta modulo doctrina: /admin -> /asistente

Plan D (interfaz doctrina supervisor/operador): el modulo 'doctrina' fue
insertado en d5e6f7a8b9c1 con ruta '/admin/doctrina', pero la pagina vive en
'/asistente/doctrina' (ConsultaLayout filtra permisos por /asistente/). Corrige
la ruta para que el sidebar dinamico del asistente muestre el modulo.

Revision ID: e6f7a8b9c1d2
Revises: d5e6f7a8b9c1
Create Date: 2026-08-16
"""

from __future__ import annotations

from alembic import op

revision: str = "e6f7a8b9c1d2"
down_revision: str | None = "d5e6f7a8b9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE modulo SET ruta = '/asistente/doctrina' WHERE clave = 'doctrina'")


def downgrade() -> None:
    op.execute("UPDATE modulo SET ruta = '/admin/doctrina' WHERE clave = 'doctrina'")
