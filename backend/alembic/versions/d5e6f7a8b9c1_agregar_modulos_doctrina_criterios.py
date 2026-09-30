"""agregar modulos doctrina y criterios al catalogo (Plan A)

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b9
Create Date: 2026-08-15 16:10:00.000000

Plan A: módulos nuevos de permisos:
- 'doctrina'  -> flujo de aprobación y doctrina global (supervisor/operador).
- 'criterios' -> vista admin de criterios (solo administrador, gestión).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c1"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUEVOS_MODULOS: list[tuple[str, str, str, str, int]] = [
    ("doctrina", "Doctrina", "Doctrina global y aprobaciones", "/admin/doctrina", 14),
    ("criterios", "Criterios", "Criterios del asistente (admin)", "/admin/criterios", 15),
]


def upgrade() -> None:
    """Inserta doctrina/criterios en el catálogo de módulos."""
    for clave, nombre, descripcion, ruta, orden in NUEVOS_MODULOS:
        op.execute(
            sa.text(
                "INSERT INTO modulo (clave, nombre, descripcion, ruta, orden) "
                "VALUES (:clave, :nombre, :descripcion, :ruta, :orden) "
                "ON CONFLICT (clave) DO NOTHING"
            ).bindparams(
                clave=clave, nombre=nombre, descripcion=descripcion, ruta=ruta, orden=orden
            )
        )


def downgrade() -> None:
    """Elimina doctrina/criterios del catálogo."""
    for clave, _nombre, _descripcion, _ruta, _orden in NUEVOS_MODULOS:
        op.execute(sa.text("DELETE FROM modulo WHERE clave = :clave").bindparams(clave=clave))
