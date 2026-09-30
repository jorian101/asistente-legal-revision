"""renombra LEY1970_CP/CPP a CP/CPP y corrige nombre legal completo

Corrige el error histórico: el Código Penal no es Ley 1970 sino
Decreto Ley 10426 (1972) elevado por Ley 1768 (1997). Solo el CPP es Ley 1970.

Revision ID: f9e8d7c6b5a4
Revises: e171160a7560
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f9e8d7c6b5a4"
down_revision: str | None = "3be1a22fab0d"
branch_labels = None
depends_on = None


# Nombres legales canónicos
NOMBRE_CP = "Código Penal (Decreto Ley Nº 10426 de 23 de agosto de 1972, elevado a rango de Ley por Ley Nº 1768 de 10 de marzo de 1997)"
NOMBRE_CPP = "Código de Procedimiento Penal (Ley Nº 1970 de 1999)"


def upgrade() -> None:
    conn = op.get_bind()
    # CP: LEY1970_CP -> CP
    conn.execute(
        sa.text("""
        UPDATE norma
        SET abreviatura = 'CP',
            nombre = :nombre_cp
        WHERE abreviatura = 'LEY1970_CP'
    """),
        {"nombre_cp": NOMBRE_CP},
    )
    # CPP: LEY1970_CPP -> CPP
    conn.execute(
        sa.text("""
        UPDATE norma
        SET abreviatura = 'CPP',
            nombre = :nombre_cpp
        WHERE abreviatura = 'LEY1970_CPP'
    """),
        {"nombre_cpp": NOMBRE_CPP},
    )
    # Asegurar que normas CP/CPP recién creadas tengan el nombre largo si
    # fueron insertadas ya con la nueva abreviatura pero nombre corto derivado.
    conn.execute(
        sa.text("""
        UPDATE norma SET nombre = :nombre_cp
        WHERE abreviatura = 'CP' AND (nombre = 'CP' OR nombre = 'LEY1970CP' OR nombre LIKE 'LEY1970%')
    """),
        {"nombre_cp": NOMBRE_CP},
    )
    conn.execute(
        sa.text("""
        UPDATE norma SET nombre = :nombre_cpp
        WHERE abreviatura = 'CPP' AND (nombre = 'CPP' OR nombre = 'LEY1970CPP' OR nombre LIKE 'LEY1970%')
    """),
        {"nombre_cpp": NOMBRE_CPP},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
        UPDATE norma SET abreviatura = 'LEY1970_CP', nombre = 'LEY1970CP'
        WHERE abreviatura = 'CP'
    """)
    )
    conn.execute(
        sa.text("""
        UPDATE norma SET abreviatura = 'LEY1970_CPP', nombre = 'LEY1970CPP'
        WHERE abreviatura = 'CPP'
    """)
    )
