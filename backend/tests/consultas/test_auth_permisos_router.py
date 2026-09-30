"""Tests HTTP del endpoint GET /auth/permisos (sidebar dinámico).

Verifica que el usuario autenticado recibe sus módulos activos con permisos
efectivos, y que el admin ve el catálogo completo con full.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.domain.entities.usuario import Usuario

ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Otro",
)
OPERADOR = Usuario(
    id=2,
    nombre="Operador",
    carnet="8012345",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Fiscal",
)


@pytest.fixture
def client():
    from src.main import app

    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_permisos_requiere_autenticacion(client: TestClient) -> None:
    resp = client.get("/auth/permisos")
    assert resp.status_code == 401


def test_permisos_devuelve_modulos_con_permisos(client: TestClient) -> None:
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: OPERADOR
    app.dependency_overrides[deps.get_permiso_repo_dep] = lambda: AsyncMock()

    # Mockear mis_permisos para no depender de BD real.
    from src.application.permisos import mis_permisos
    from src.domain.entities.permiso import PermisoEfectivo

    async def _fake_execute(permiso_repo, usuario_id: int, rol: str):
        return [
            mis_permisos.ModuloPermisoDTO(
                clave="consultar",
                nombre="Consultar",
                descripcion="Consulta jurídica RAG",
                ruta="/asistente/consultar",
                orden=10,
                efectivo=PermisoEfectivo(
                    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=True
                ),
            ),
            mis_permisos.ModuloPermisoDTO(
                clave="borradores",
                nombre="Borradores",
                descripcion="Generación de borradores jurídicos",
                ruta="/asistente/borradores",
                orden=12,
                efectivo=PermisoEfectivo(
                    puede_crear=False, puede_leer=True, puede_actualizar=False, puede_eliminar=False
                ),
            ),
        ]

    original = mis_permisos.execute
    mis_permisos.execute = _fake_execute
    try:
        resp = client.get("/auth/permisos")
    finally:
        mis_permisos.execute = original

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    consultar = next(m for m in body if m["clave"] == "consultar")
    assert consultar["puede_leer"] is True
    assert consultar["ruta"] == "/asistente/consultar"
    borradores = next(m for m in body if m["clave"] == "borradores")
    assert borradores["puede_crear"] is False
    assert borradores["puede_leer"] is True


def test_permisos_admin_ve_catalogo_completo_full(client: TestClient) -> None:
    """El admin siempre ve full en todos los módulos del catálogo."""
    from src.main import app

    app.dependency_overrides[deps.get_current_user] = lambda: ADMIN

    # Usar el permiso repo real con una sesión fake vacía no alcanza; mejor
    # mockear mis_permisos con el catálogo completo.
    from src.application.permisos import mis_permisos
    from src.domain.entities.permiso import Modulo, PermisoEfectivo

    modulos = [
        Modulo(clave=f"m{i}", nombre=f"M{i}", descripcion="", ruta=f"/admin/x{i}", orden=i)
        for i in range(3)
    ]

    async def _fake_execute(permiso_repo, usuario_id: int, rol: str):
        assert rol == "administrador"
        return [
            mis_permisos.ModuloPermisoDTO(
                clave=m.clave,
                nombre=m.nombre,
                descripcion=m.descripcion,
                ruta=m.ruta,
                orden=m.orden,
                efectivo=PermisoEfectivo(
                    puede_crear=True, puede_leer=True, puede_actualizar=True, puede_eliminar=True
                ),
            )
            for m in modulos
        ]

    original = mis_permisos.execute
    mis_permisos.execute = _fake_execute
    try:
        resp = client.get("/auth/permisos")
    finally:
        mis_permisos.execute = original

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    for m in body:
        assert m["puede_crear"] is True
        assert m["puede_leer"] is True
