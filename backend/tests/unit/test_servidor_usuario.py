"""La app de usuario sirve la API bajo /api y el frontend (con fallback de SPA) en /."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import src.main  # noqa: F401 — importarlo al recolectar: en frio supera el timeout de 5 s


def _cliente(monkeypatch, tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    import src.servidor_usuario as modulo

    # Sin `with`: no corre el lifespan (necesitaria PostgreSQL).
    return TestClient(importlib.reload(modulo).servidor)


def test_sirve_archivos_del_frontend(monkeypatch, tmp_path) -> None:
    r = _cliente(monkeypatch, tmp_path).get("/app.js")

    assert r.status_code == 200
    assert "console.log" in r.text


def test_ruta_del_cliente_devuelve_index(monkeypatch, tmp_path) -> None:
    r = _cliente(monkeypatch, tmp_path).get("/consultas/asistente")

    assert r.status_code == 200
    assert "root" in r.text


def test_api_montada_bajo_api(monkeypatch, tmp_path) -> None:
    r = _cliente(monkeypatch, tmp_path).get("/api/admin/metricas/salud")

    # Ruta protegida: responde la API (401/403), no el index del frontend.
    assert r.status_code in (401, 403)
    assert "root" not in r.text
