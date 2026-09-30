"""Tests del UC de auditoria (Trail of Bits R6).

registrar_auditoria persiste una accion sensitiva; listar_auditoria la
consulta. Usa fake repo (sin DB) para probar el contrato.
"""

from __future__ import annotations

import pytest

from src.application.admin.audit import listar_auditoria, registrar_auditoria
from src.domain.value_objects.registro_auditoria import RegistroAuditoria


class FakeAuditRepo:
    """AuditLogRepo in-memory."""

    def __init__(self) -> None:
        self.registros: list[RegistroAuditoria] = []

    async def registrar(self, registro: RegistroAuditoria) -> None:
        self.registros.append(registro)

    async def listar(
        self,
        accion: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RegistroAuditoria]:
        items = self.registros
        if accion is not None:
            items = [r for r in items if r.accion == accion]
        return items[offset : offset + limit]


@pytest.mark.asyncio
async def test_registrar_auditoria_persiste_accion() -> None:
    """R6: registrar_auditoria persiste la accion con usuario y entidad."""
    repo = FakeAuditRepo()

    await registrar_auditoria(
        repo,
        accion="publicar_borrador",
        usuario_id=3,
        entidad="borrador",
        entidad_id=777,
    )

    assert len(repo.registros) == 1
    reg = repo.registros[0]
    assert reg.accion == "publicar_borrador"
    assert reg.usuario_id == 3
    assert reg.entidad == "borrador"
    assert reg.entidad_id == 777


@pytest.mark.asyncio
async def test_registrar_login_fallido_sin_usuario() -> None:
    """R6: login fallido se registra con usuario None y detalle de contexto."""
    repo = FakeAuditRepo()

    await registrar_auditoria(
        repo,
        accion="login_fallido",
        usuario_id=None,
        entidad="usuario",
        detalle={"carnet": "abc123", "ip": "127.0.0.1"},
    )

    reg = repo.registros[0]
    assert reg.usuario_id is None
    assert reg.detalle == {"carnet": "abc123", "ip": "127.0.0.1"}


@pytest.mark.asyncio
async def test_listar_auditoria_filtra_por_accion() -> None:
    """R6: listar_auditoria filtra por accion (panel admin)."""
    repo = FakeAuditRepo()
    await registrar_auditoria(repo, accion="login", usuario_id=1, entidad="usuario")
    await registrar_auditoria(
        repo,
        accion="crear_expediente",
        usuario_id=2,
        entidad="expediente",
        entidad_id=9,
    )
    await registrar_auditoria(repo, accion="login", usuario_id=1, entidad="usuario")

    logins = await listar_auditoria(repo, accion="login")
    assert len(logins) == 2
    assert all(r.accion == "login" for r in logins)

    todos = await listar_auditoria(repo)
    assert len(todos) == 3


@pytest.mark.asyncio
async def test_registro_es_inmutable() -> None:
    """RegistroAuditoria es frozen dataclass (no se muta post-persistencia)."""
    repo = FakeAuditRepo()
    await registrar_auditoria(repo, accion="login", usuario_id=1)

    with pytest.raises(AttributeError):
        repo.registros[0].accion = "otra_accion"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_registrar_auditoria_segura_no_lanza_pero_deja_log(caplog) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from src.application.admin.audit import registrar_auditoria_segura

    repo = MagicMock(registrar=AsyncMock(side_effect=RuntimeError("bd caida")))

    with caplog.at_level("WARNING"):
        await registrar_auditoria_segura(repo, accion="asignar_permisos", usuario_id=1)

    assert "asignar_permisos" in caplog.text
