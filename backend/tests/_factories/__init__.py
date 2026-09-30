"""Paquete factories de tests. Helpers `make_X(**overrides)` por entidad de dominio.

Re-export para uso: `from tests._factories import make_usuario, make_admin, ...`
"""

from tests._factories._factories import (  # noqa: F401
    make_admin,
    make_borrador,
    make_expediente,
    make_fragmento,
    make_norma,
    make_supervisor,
    make_usuario,
)
