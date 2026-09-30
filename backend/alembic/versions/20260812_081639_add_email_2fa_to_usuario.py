"""add email y 2fa campos a usuario

Revision ID: 5a1b2c3d4e5f
Revises: 4ffdd6dca550
Create Date: 2026-08-12 00:00:00.000000

Campos para 2FA email (Fase 2 plan jurado):
- email TEXT NULL UNIQUE
- email_verificado BOOLEAN NOT NULL DEFAULT false
- codigo_2fa_hash TEXT NULL (SHA-256 del codigo 6 digitos)
- codigo_2fa_expira TIMESTAMPTZ NULL
- intentos_codigo INTEGER NOT NULL DEFAULT 0 (contador intentos invalidos)
- bloqueado_hasta TIMESTAMPTZ NULL (lockout tras 3 fallidos, admin desbloquea)

Sprint 1 Auth extendido para 2FA simplificado: carnet+password -> codigo email -> JWT.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "4ffdd6dca550"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega columnas 2FA a tabla usuario."""
    # email + email_verificado
    op.add_column(
        "usuario",
        sa.Column("email", sa.String(), nullable=True, unique=True),
    )
    op.add_column(
        "usuario",
        sa.Column(
            "email_verificado", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    # 2FA: codigo hash + expiracion + intentos + bloqueo
    op.add_column(
        "usuario",
        sa.Column("codigo_2fa_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "usuario",
        sa.Column("codigo_2fa_expira", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "usuario",
        sa.Column("intentos_codigo", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "usuario",
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
    )
    # Indice para busqueda rapida por email (ya unique=True lo crea, pero explicit es mas claro)


def downgrade() -> None:
    """Remueve columnas 2FA de tabla usuario."""
    op.drop_column("usuario", "bloqueado_hasta")
    op.drop_column("usuario", "intentos_codigo")
    op.drop_column("usuario", "codigo_2fa_expira")
    op.drop_column("usuario", "codigo_2fa_hash")
    op.drop_column("usuario", "email_verificado")
    op.drop_column("usuario", "email")
