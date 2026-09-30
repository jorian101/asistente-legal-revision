"""agregar modulo obras al catalogo (fix permisos post 0af2a54)

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-08-23 00:00:00.000000

Nuevo modulo 'obras': carga, publicacion y eliminacion de obrados del
expediente. Desacopla esas operaciones de 'expedientes.actualizar' para que
el operador pueda trabajar archivos sin poder editar el expediente (bug
introducido por commit 0af2a54, que compartia el guard).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULO_OBRAS = (
    "obras",
    "Obras",
    "Carga, publicación y eliminación de obrados del expediente",
    "/asistente/expedientes",
    16,
)


def upgrade() -> None:
    """Inserta el modulo obras en el catalogo."""
    clave, nombre, descripcion, ruta, orden = MODULO_OBRAS
    op.execute(
        sa.text(
            "INSERT INTO modulo (clave, nombre, descripcion, ruta, orden) "
            "VALUES (:clave, :nombre, :descripcion, :ruta, :orden) "
            "ON CONFLICT (clave) DO NOTHING"
        ).bindparams(clave=clave, nombre=nombre, descripcion=descripcion, ruta=ruta, orden=orden)
    )


def downgrade() -> None:
    """Elimina el modulo obras del catalogo."""
    op.execute(sa.text("DELETE FROM modulo WHERE clave = 'obras'"))
