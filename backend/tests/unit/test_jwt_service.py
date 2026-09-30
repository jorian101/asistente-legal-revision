"""Tests unitarios de PyJwtService (Sprint 1, F1.4).

No tocan BD. Verifican encode/decode de access token y formato del refresh.
"""

from __future__ import annotations

import jwt
import pytest

from src.adapters.jwt_service import PyJwtService


def test_access_token_roundtrip() -> None:
    svc = PyJwtService(secret="test-secret")
    token = svc.crear_access_token(usuario_id=42, rol="administrador")

    payload = svc.verificar_access_token(token)
    assert payload["sub"] == "42"
    assert payload["rol"] == "administrador"
    assert "exp" in payload


def test_access_token_tampered_rejected() -> None:
    svc = PyJwtService(secret="test-secret")
    token = svc.crear_access_token(usuario_id=1, rol="operador_juridico")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")

    with pytest.raises(jwt.InvalidTokenError):
        svc.verificar_access_token(tampered)


def test_refresh_token_is_opaque_and_unique() -> None:
    svc = PyJwtService(secret="test-secret")
    a = svc.crear_refresh_token()
    b = svc.crear_refresh_token()

    assert a != b
    assert "." not in a  # no parece JWT (no tiene 3 partes separadas por punto)
    assert len(a) >= 32
