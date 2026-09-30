"""Chequeo estatico de docker-compose.yml (Regla 1 y F-26)."""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.yml"


def _servicios() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_postgres_solo_publica_en_loopback() -> None:
    puertos = _servicios()["postgres"]["ports"]

    assert puertos, "postgres debe publicar su puerto para el backend en el host"
    assert all(str(p).startswith("127.0.0.1:") for p in puertos)


def test_qdrant_no_publica_puertos_al_host() -> None:
    qdrant = _servicios()["qdrant"]

    assert "ports" not in qdrant
    assert qdrant["expose"]


def test_las_imagenes_no_usan_latest() -> None:
    con_latest = {
        nombre: s["image"]
        for nombre, s in _servicios().items()
        if s["image"].endswith(":latest") or ":" not in s["image"]
    }

    assert con_latest == {}
