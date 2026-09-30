"""Tests HTTP del guard require_permiso(clave, operacion).

Verifica el enforcement en backend (Regla 2 Trail of Bits):
- 200 si el permiso efectivo permite la operacion.
- 403 si el permiso efectivo la deniega.
- 403 si el módulo no existe en los permisos del usuario.

El resolver_permisos_usuario (que consulta BD) ya está cubierto por
test_permisos_usecases.py; aquí se mockea para aislar el comportamiento
del guard sobre el resultado efectivo.
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.adapters.http.dependencies import get_current_user, get_db_session, require_permiso
from src.domain.entities.permiso import PermisoEfectivo
from src.domain.entities.usuario import Usuario

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
    app = FastAPI()

    @app.get("/probe-corpus")
    async def probe(
        _user: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    ):
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: OPERADOR
    # nunca usada (resolver mockeado)
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _efectivo(puede_leer: bool) -> dict[str, PermisoEfectivo]:
    return {
        "corpus": PermisoEfectivo(
            puede_crear=False,
            puede_leer=puede_leer,
            puede_actualizar=False,
            puede_eliminar=False,
        )
    }


def test_guard_200_con_permiso(client: TestClient) -> None:
    with patch(
        "src.application.permisos.resolver_permisos_usuario.execute",
        new=AsyncMock(return_value=_efectivo(True)),
    ):
        resp = client.get("/probe-corpus")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_guard_403_sin_permiso(client: TestClient) -> None:
    with patch(
        "src.application.permisos.resolver_permisos_usuario.execute",
        new=AsyncMock(return_value=_efectivo(False)),
    ):
        resp = client.get("/probe-corpus")
    assert resp.status_code == 403
    assert "corpus" in resp.json()["detail"]


def test_guard_403_si_modulo_no_existe_en_permisos(client: TestClient) -> None:
    # El usuario no tiene el módulo en su mapa de permisos efectivos.
    with patch(
        "src.application.permisos.resolver_permisos_usuario.execute",
        new=AsyncMock(return_value={"otro_modulo": _efectivo(True)["corpus"]}),
    ):
        resp = client.get("/probe-corpus")
    assert resp.status_code == 403
