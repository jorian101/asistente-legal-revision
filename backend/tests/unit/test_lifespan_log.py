"""El lifespan informa por logging (no por print) al reconciliar consultas viejas."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from src import main


@pytest.mark.asyncio
async def test_reconciliacion_omitida_se_registra_con_logging(monkeypatch, caplog, capsys) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    with (
        patch.object(main, "_load_config_cache"),
        patch(
            "src.adapters.http.dependencies.get_session_factory",
            side_effect=RuntimeError("sin base de datos"),
        ),
        caplog.at_level(logging.WARNING, logger="src.main"),
    ):
        async with main.lifespan(MagicMock()):
            pass

    assert "reconciliación omitida" in caplog.text
    assert "[lifespan]" not in capsys.readouterr().out
