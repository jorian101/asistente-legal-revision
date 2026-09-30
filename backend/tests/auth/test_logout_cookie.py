"""El logout debe borrar la cookie del refresh token en el navegador.

`logout_endpoint` llamaba `response.delete_cookie` sobre el Response inyectado y luego
devolvia un Response nuevo: FastAPI no fusiona las cabeceras del inyectado, asi que la
cookie httpOnly seguia en el navegador.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.main import app


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    auth = MagicMock()
    auth.revocar_refresh_token = AsyncMock()
    app.dependency_overrides[deps.get_auth_repo] = lambda: auth
    yield TestClient(app), auth
    app.dependency_overrides.clear()


def test_logout_revoca_el_token_y_borra_la_cookie(client) -> None:
    http, auth = client
    http.cookies.set("refresh_token", "token-opaco")

    resp = http.post("/auth/logout")

    assert resp.status_code == 204
    auth.revocar_refresh_token.assert_awaited_once()
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie
