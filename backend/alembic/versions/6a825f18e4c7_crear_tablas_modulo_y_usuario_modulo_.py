"""crear tablas modulo y usuario_modulo_permiso

Revision ID: 6a825f18e4c7
Revises: 4f2a8c6d3e10
Create Date: 2026-08-15 12:46:43.080523

Tablas del sistema de permisos CRUD por usuario (decision
`plan/permisos-crud-modulos`):
- `modulo`: catálogo fijo de los 11 módulos del sistema (seed abajo).
- `usuario_modulo_permiso`: overrides de permisos CRUD por usuario
  (NULL = seguir default del rol; TRUE/FALSE = override explícito).

El default por rol vive en código (domain/entities/permiso.py).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a825f18e4c7"
down_revision: str | Sequence[str] | None = "4f2a8c6d3e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Seed del catálogo fijo de módulos: (clave, nombre, descripcion, ruta, orden).
MODULOS_SEED: list[tuple[str, str, str, str, int]] = [
    ("usuarios", "Usuarios", "Gestión de usuarios y perfiles", "/admin/usuarios", 1),
    ("corpus", "Corpus Jurídico", "Indexación y configuración de normativa", "/admin/corpus", 2),
    ("metricas", "Métricas", "Monitoreo del RAG, latencia y uso", "/admin/metricas", 3),
    (
        "sala_control",
        "Sala de Control",
        "Trazabilidad del pipeline RAG en vivo",
        "/admin/sala-control",
        4,
    ),
    ("auditoria", "Auditoría", "Log de acciones sensitivas (R6)", "/admin/auditoria", 5),
    (
        "consultas_rag",
        "Consultas RAG",
        "Auditoría del historial de consultas con filtros",
        "/admin/consultas",
        6,
    ),
    (
        "expedientes",
        "Expedientes",
        "Apertura y gestión de expedientes",
        "/asistente/expedientes",
        7,
    ),
    ("consultar", "Consultar", "Consulta jurídica RAG", "/asistente/consultar", 8),
    (
        "conversaciones",
        "Conversaciones",
        "Historial de consultas del chat",
        "/asistente/conversaciones",
        9,
    ),
    ("borradores", "Borradores", "Generación de borradores jurídicos", "/asistente/borradores", 10),
    ("chats", "Chats privados", "Espacios de trabajo por expediente", "/asistente/chats", 11),
]


def upgrade() -> None:
    """Crea tablas modulo y usuario_modulo_permiso + seed de módulos."""
    op.create_table(
        "modulo",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("GENERATED ALWAYS AS IDENTITY"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("clave", sa.String(), nullable=False),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("descripcion", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("ruta", sa.String(), nullable=False),
        sa.Column("orden", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave"),
    )
    op.create_table(
        "usuario_modulo_permiso",
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("modulo_id", sa.BigInteger(), nullable=False),
        sa.Column("puede_crear", sa.Boolean(), nullable=True),
        sa.Column("puede_leer", sa.Boolean(), nullable=True),
        sa.Column("puede_actualizar", sa.Boolean(), nullable=True),
        sa.Column("puede_eliminar", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["modulo_id"], ["modulo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "modulo_id"),
    )
    op.create_index(
        "usuario_modulo_permiso_modulo_idx",
        "usuario_modulo_permiso",
        ["modulo_id"],
        unique=False,
    )
    op.create_index(
        "usuario_modulo_permiso_usuario_idx",
        "usuario_modulo_permiso",
        ["usuario_id"],
        unique=False,
    )
    for clave, nombre, descripcion, ruta, orden in MODULOS_SEED:
        op.execute(
            sa.text(
                "INSERT INTO modulo (clave, nombre, descripcion, ruta, orden) "
                "VALUES (:clave, :nombre, :descripcion, :ruta, :orden)"
            ).bindparams(
                clave=clave, nombre=nombre, descripcion=descripcion, ruta=ruta, orden=orden
            )
        )


def downgrade() -> None:
    """Drop tablas modulo y usuario_modulo_permiso."""
    op.drop_index("usuario_modulo_permiso_usuario_idx", table_name="usuario_modulo_permiso")
    op.drop_index("usuario_modulo_permiso_modulo_idx", table_name="usuario_modulo_permiso")
    op.drop_table("usuario_modulo_permiso")
    op.drop_table("modulo")
