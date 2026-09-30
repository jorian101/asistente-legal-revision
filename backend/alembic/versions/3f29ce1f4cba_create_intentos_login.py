"""create intentos_login table

Revision ID: 3f29ce1f4cba
Revises: d8afe037caab
Create Date: 2026-08-02 22:31:00.000000

Tabla `intentos_login` para soportar Regla 2 Trail of Bits:
- rate limit 5 intentos/min por IP
- lockout tras 10 intentos fallidos por carnet en ventana de 1 hora
- solo Admin puede desbloquear (no auto-unlock)

Indices compuestos para las 2 queries del use case login.py:
  1. contar_intentos_por_ip(ip, desde=now-1min) -> WHERE ip=? AND timestamp>=?
  2. contar_intentos_fallidos(carnet, desde=now-1h) -> WHERE carnet=? AND exitoso=false AND timestamp>=?

Sprint 1 Auth, Migracion M3 del plan v3.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f29ce1f4cba"
down_revision: str | Sequence[str] | None = "d8afe037caab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea tabla intentos_login."""
    op.create_table(
        "intentos_login",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("carnet", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("exitoso", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indice compuesto para query lockout por carnet: WHERE carnet=? AND exitoso=false AND timestamp>=?
    op.create_index(
        "ix_intentos_login_carnet_timestamp",
        "intentos_login",
        ["carnet", "timestamp"],
        unique=False,
    )
    # Indice compuesto para query rate limit por IP: WHERE ip=? AND timestamp>=?
    op.create_index(
        "ix_intentos_login_ip_timestamp",
        "intentos_login",
        ["ip", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tabla intentos_login."""
    op.drop_index("ix_intentos_login_ip_timestamp", table_name="intentos_login")
    op.drop_index("ix_intentos_login_carnet_timestamp", table_name="intentos_login")
    op.drop_table("intentos_login")
