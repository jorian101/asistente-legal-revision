"""Contrato HTTP de /auth: códigos de error y cookie del refresh token (R2).

Los casos de uso se sustituyen por dobles: aquí se prueba el mapeo excepción -> HTTP y
los atributos de la cookie (httpOnly, Secure, SameSite=Strict), no la lógica de negocio.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.auth import login, refresh_token, verificar_2fa
from src.main import app


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    install_permiso_repo_override(app)
    app.dependency_overrides[deps.get_auth_repo] = lambda: MagicMock()
    app.dependency_overrides[deps.get_email_service] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _cookie_segura(resp) -> str:
    cabecera = resp.headers.get("set-cookie", "").lower()
    assert "refresh_token=" in cabecera
    assert "httponly" in cabecera
    assert "secure" in cabecera
    assert "samesite=strict" in cabecera
    return cabecera


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (login.RateLimitError(), 429),
        (login.LockoutError(), 423),
        (login.ServicioEmailNoDisponibleError(), 503),
        (login.LoginError(), 401),
    ],
)
def test_login_mapea_los_errores_del_caso_de_uso(client, monkeypatch, error, codigo) -> None:
    monkeypatch.setattr(login, "execute", AsyncMock(side_effect=error))

    resp = client.post("/auth/login", json={"carnet": "10702191", "password": "secreto1"})

    assert resp.status_code == codigo


def test_login_que_requiere_2fa_no_emite_cookie(client, monkeypatch) -> None:
    monkeypatch.setattr(login, "execute", AsyncMock(side_effect=login.Requiere2FaError("10702191")))

    resp = client.post("/auth/login", json={"carnet": "10702191", "password": "secreto1"})

    assert resp.status_code == 200
    assert resp.json()["requiere_2fa"] is True
    assert "set-cookie" not in resp.headers


def test_login_ok_entrega_el_access_token_y_la_cookie_segura(client, monkeypatch) -> None:
    ok = login.LoginResponse(
        access_token="acceso",
        refresh_token="refresh-1",
        rol="operador_juridico",
        carnet="10702191",
        nombre="Op",
        id=5,
        cargo="Vocal Relator",
    )
    monkeypatch.setattr(login, "execute", AsyncMock(return_value=ok))

    resp = client.post("/auth/login", json={"carnet": "10702191", "password": "secreto1"})

    assert resp.status_code == 200
    assert resp.json()["access_token"] == "acceso"
    assert resp.json()["cargo"] == "Vocal Relator"  # el header lo muestra junto al rol
    assert "refresh_token" not in resp.json()  # el refresh solo viaja en la cookie
    assert "refresh-1" in _cookie_segura(resp)


def test_verificar_2fa_invalido_es_401(client, monkeypatch) -> None:
    monkeypatch.setattr(
        verificar_2fa,
        "execute",
        AsyncMock(side_effect=verificar_2fa.Verificar2FaError("Código inválido.")),
    )

    resp = client.post("/auth/verificar-2fa", json={"carnet": "10702191", "codigo": "123456"})

    assert resp.status_code == 401


def test_refresh_sin_cookie_es_401(client) -> None:
    assert client.post("/auth/refresh").status_code == 401


@pytest.mark.parametrize(
    "error", [refresh_token.ReplayError(), refresh_token.RefreshTokenError(), RuntimeError()]
)
def test_refresh_con_token_invalido_es_401(client, monkeypatch, error) -> None:
    monkeypatch.setattr(refresh_token, "execute", AsyncMock(side_effect=error))
    client.cookies.set("refresh_token", "viejo")

    assert client.post("/auth/refresh").status_code == 401


def test_refresh_ok_rota_la_cookie_con_atributos_seguros(client, monkeypatch) -> None:
    resultado = MagicMock(access_token="acceso-nuevo", refresh_token="refresh-nuevo")
    monkeypatch.setattr(refresh_token, "execute", AsyncMock(return_value=resultado))
    client.cookies.set("refresh_token", "viejo")

    resp = client.post("/auth/refresh")

    assert resp.status_code == 200
    assert resp.json() == {"access_token": "acceso-nuevo"}
    assert "refresh-nuevo" in _cookie_segura(resp)
