"""renombrar modulos obras, borradores y corpus (labels de la UI)

Revision ID: 20cf249ed939
Revises: e3b9c5d7a1f2
Create Date: 2026-09-22 00:00:00.000000

El sidebar y el dashboard muestran modulo.nombre. Se alinea con
frontend/src/config/modulosPorRol.ts: dos modulos ya no comparten la
etiqueta de obrados y "Corpus jurídico" va en minuscula como en su pagina.
Solo UPDATE de nombre por clave: no destructiva.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20cf249ed939"
down_revision: str | Sequence[str] | None = "e3b9c5d7a1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# clave -> (nombre anterior, nombre nuevo)
RENOMBRES = {
    "obras": ("Obras", "Obrados del expediente"),
    "borradores": ("Borradores", "Obrados generados"),
    "corpus": ("Corpus Jurídico", "Corpus jurídico"),
}


def _renombrar(indice: int) -> None:
    for clave, nombres in RENOMBRES.items():
        op.execute(
            sa.text("UPDATE modulo SET nombre = :nombre WHERE clave = :clave").bindparams(
                nombre=nombres[indice], clave=clave
            )
        )


def upgrade() -> None:
    """Aplica los nombres nuevos."""
    _renombrar(1)


def downgrade() -> None:
    """Restaura los nombres anteriores."""
    _renombrar(0)
