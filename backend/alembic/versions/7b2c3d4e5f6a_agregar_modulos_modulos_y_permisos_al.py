"""agregar modulos modulos y permisos al catalogo

Revision ID: 7b2c3d4e5f6a
Revises: 6a825f18e4c7
Create Date: 2026-08-15 13:30:00.000000

Fase 2 del plan permisos-crud-modulos: la sección admin necesita dos módulos
nuevos en el catálogo para editar módulos (Modulos.tsx) y asignar permisos
CRUD por usuario (PermisosUsuario.tsx):
- 'modulos' → /admin/modulos  (orden 7)
- 'permisos' → /admin/permisos (orden 8)

Los módulos de consulta se reordenan (expedientes 9, consultar 10,
conversaciones 11, borradores 12, chats 13) para mantener el orden lógico
del sidebar: admin primero, consulta después.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2c3d4e5f6a"
down_revision: str | Sequence[str] | None = "6a825f18e4c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUEVOS_MODULOS: list[tuple[str, str, str, str, int]] = [
    ("modulos", "Módulos", "Catálogo de módulos y su configuración", "/admin/modulos", 7),
    ("permisos", "Permisos", "Permisos CRUD por módulo y usuario", "/admin/permisos", 8),
]

REORDEN: dict[str, int] = {
    "expedientes": 9,
    "consultar": 10,
    "conversaciones": 11,
    "borradores": 12,
    "chats": 13,
}


def upgrade() -> None:
    """Inserta modulos/permisos y reordena el resto."""
    for clave, nombre, descripcion, ruta, orden in NUEVOS_MODULOS:
        op.execute(
            sa.text(
                "INSERT INTO modulo (clave, nombre, descripcion, ruta, orden) "
                "VALUES (:clave, :nombre, :descripcion, :ruta, :orden)"
            ).bindparams(
                clave=clave, nombre=nombre, descripcion=descripcion, ruta=ruta, orden=orden
            )
        )
    for clave, orden in REORDEN.items():
        op.execute(
            sa.text("UPDATE modulo SET orden = :orden WHERE clave = :clave").bindparams(
                clave=clave, orden=orden
            )
        )


def downgrade() -> None:
    """Elimina los módulos nuevos y restaura el orden original."""
    for clave in ("permisos", "modulos"):
        op.execute(sa.text("DELETE FROM modulo WHERE clave = :clave").bindparams(clave=clave))
    orden_original: dict[str, int] = {
        "expedientes": 7,
        "consultar": 8,
        "conversaciones": 9,
        "borradores": 10,
        "chats": 11,
    }
    for clave, orden in orden_original.items():
        op.execute(
            sa.text("UPDATE modulo SET orden = :orden WHERE clave = :clave").bindparams(
                clave=clave, orden=orden
            )
        )
