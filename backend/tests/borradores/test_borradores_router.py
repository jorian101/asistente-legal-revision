"""Tests HTTP del router /borradores (Sprint 6 Fase 4.1).

TDD con TestClient + dependency_overrides: no toca DB, Ollama, ni Qdrant.
Reemplaza use cases y auth por fakes/mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.adapters.http import dependencies_borradores as bdeps
from src.domain.entities.borrador import Borrador
from src.domain.entities.usuario import Usuario
from src.domain.exceptions import (
    BorradorNoPropioError,
    PlantillaNoImplementadaError,
)
from src.main import app as fastapi_app

OPERADOR = Usuario(
    id=2,
    nombre="Ope",
    carnet="6000002",
    password_hash="x",
    rol="operador_juridico",
    activo=True,
    cargo="Auditor",
)
ADMIN = Usuario(
    id=1,
    nombre="Admin",
    carnet="9000001",
    password_hash="x",
    rol="administrador",
    activo=True,
    cargo="Auditor",
)
SUPERVISOR = Usuario(
    id=3,
    nombre="Sup",
    carnet="6000003",
    password_hash="x",
    rol="supervisor",
    activo=True,
    cargo="Vocal Relator",
)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def _override_current_user(user: Usuario | None) -> None:
    if user is None:
        from fastapi import HTTPException, status

        def _raise() -> Usuario:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        fastapi_app.dependency_overrides[deps.get_current_user] = _raise
    else:
        fastapi_app.dependency_overrides[deps.get_current_user] = lambda: user


def _async_gen(tokens: list[str]) -> AsyncIterator[str]:
    async def _g():
        for t in tokens:
            yield t

    return _g()


def _override_generar_uc(
    *,
    borrador_id: int | None = 77,
    tipo: str = "auto_vista_consulta",
    tokens: list[str] | None = None,
    error: Exception | None = None,
) -> MagicMock:
    uc = MagicMock()

    if error is not None:
        uc.ejecutar = AsyncMock(side_effect=error)
        fastapi_app.dependency_overrides[bdeps.get_generar_borrador] = lambda: uc
        return uc

    result = MagicMock()
    result.borrador_id = borrador_id
    result.tipo_respuesta = tipo
    result.stream = _async_gen(tokens if tokens is not None else ["Hola ", "mundo"])
    uc.ejecutar = AsyncMock(return_value=result)
    fastapi_app.dependency_overrides[bdeps.get_generar_borrador] = lambda: uc
    return uc


def _override_publicar_uc(*, error: Exception | None = None) -> MagicMock:
    uc = MagicMock()
    if error is not None:
        uc.ejecutar = AsyncMock(side_effect=error)
    else:
        result = MagicMock(borrador_id=77, estado="publicado")
        uc.ejecutar = AsyncMock(return_value=result)
    fastapi_app.dependency_overrides[bdeps.get_publicar_borrador] = lambda: uc
    return uc


def _override_listar_uc(items: list[Borrador]) -> MagicMock:
    uc = MagicMock()
    uc.ejecutar = AsyncMock(return_value=items)
    fastapi_app.dependency_overrides[bdeps.get_listar_borradores] = lambda: uc
    return uc


def _override_obtener_uc(
    *,
    borrador: Borrador | None = None,
    error: Exception | None = None,
) -> MagicMock:
    uc = MagicMock()
    if error is not None:
        uc.ejecutar = AsyncMock(side_effect=error)
    else:
        uc.ejecutar = AsyncMock(return_value=borrador)
    fastapi_app.dependency_overrides[bdeps.get_obtener_borrador] = lambda: uc
    return uc


def _make_borrador(**kwargs: Any) -> Borrador:
    from tests._factories import make_borrador

    return make_borrador(**kwargs)


# ===== POST /borradores/generar ======================================


def test_generar_borrador_stream_response_201(client: TestClient) -> None:
    """POST /generar con supervisor -> 201 + stream text/plain."""
    _override_current_user(OPERADOR)
    _override_generar_uc(tokens=["Hola ", "mundo!"])

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "plazo de apelacion", "expediente_id": 7},
    )

    assert resp.status_code == 201
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.headers["X-Borrador-Id"] == "77"
    assert resp.headers["X-Borrador-Tipo"] == "auto_vista_consulta"
    assert resp.text == "Hola mundo!"


def test_generar_borrador_consulta_simple_sin_id(client: TestClient) -> None:
    """consulta_simple -> X-Borrador-Id vacio (no se creo borrador)."""
    _override_current_user(OPERADOR)
    _override_generar_uc(borrador_id=None, tipo="consulta_simple", tokens=["ok"])

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "que es un amparo", "expediente_id": None},
    )

    assert resp.status_code == 201
    assert resp.headers["X-Borrador-Id"] == ""
    assert resp.text == "ok"


def test_generar_borrador_admin_403(client: TestClient) -> None:
    """Admin no tiene permiso 'borradores:crear' (gestión, no produce borradores)."""
    _override_current_user(ADMIN)
    _override_generar_uc(tokens=["x"])

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "x", "expediente_id": None},
    )

    assert resp.status_code == 403
    assert "permiso" in resp.json()["detail"].lower()


def test_generar_borrador_supervisor_permitido(client: TestClient) -> None:
    """Supervisor genera y guarda obrados (auto de vista/dictamen): desde el
    QA 2026-08 se le da 'borradores.crear'."""
    _override_current_user(SUPERVISOR)
    _override_generar_uc(tokens=["x"])

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "consulta valida", "expediente_id": None},
    )

    assert resp.status_code == 201


def test_generar_sin_plantilla_422(client: TestClient) -> None:
    """PlantillaNoImplementadaError (dictamen_radicatoria) -> 422."""
    _override_current_user(OPERADOR)
    _override_generar_uc(error=PlantillaNoImplementadaError("no implementada"))

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "dictamen radicatoria", "expediente_id": 10},
    )

    assert resp.status_code == 422
    assert "no implementada" in resp.json()["detail"].lower()


def test_generar_variante_restringida_422(client: TestClient) -> None:
    """Apelación restringida sin plantilla propia -> 422 descriptivo."""
    from src.domain.exceptions import VarianteApelacionNoSoportadaError

    _override_current_user(OPERADOR)
    _override_generar_uc(
        error=VarianteApelacionNoSoportadaError("apelación restringida sin plantilla")
    )

    resp = client.post(
        "/borradores/generar",
        json={"consulta": "auto de vista", "expediente_id": 8},
    )

    assert resp.status_code == 422
    assert "restringida" in resp.json()["detail"].lower()


def test_generar_sin_auth_401(client: TestClient) -> None:
    _override_current_user(None)
    _override_generar_uc(tokens=["x"])

    resp = client.post("/borradores/generar", json={"consulta": "x"})
    assert resp.status_code == 401


def test_generar_body_invalido_422(client: TestClient) -> None:
    """Body con menos de 3 chars -> 422 (Pydantic)."""
    _override_current_user(OPERADOR)
    _override_generar_uc(tokens=["x"])

    resp = client.post("/borradores/generar", json={"consulta": "ab"})
    assert resp.status_code == 422


# ===== POST /borradores/{id}/publicar ===============================


def test_publicar_borrador_200(client: TestClient) -> None:
    """Publicar borrador propio -> 200 + estado publicado."""
    _override_current_user(OPERADOR)
    _override_publicar_uc()
    audit = _override_audit_repo()

    resp = client.post("/borradores/77/publicar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["borrador_id"] == 77
    assert body["estado"] == "publicado"
    # R6: publicar es accion sensitiva — la auditoria debe persistir (fake,
    # nunca el repo real: su await contra PG cuelga el portal anyio del
    # TestClient, ver gate run 01M0QV27Q8).
    audit.registrar.assert_awaited_once()


def test_publicar_borrador_ajeno_403(client: TestClient) -> None:
    """Publicar borrador ajeno -> 403 Regla 7."""
    _override_current_user(OPERADOR)
    _override_publicar_uc(error=BorradorNoPropioError("no es propietario"))

    resp = client.post("/borradores/999/publicar")

    assert resp.status_code == 403
    assert "propietario" in resp.json()["detail"].lower()


# ===== GET /borradores/ (listar) ====================================


def test_listar_borradores_200(client: TestClient) -> None:
    """Listar borradores de un expediente -> 200 + lista DTO."""
    _override_current_user(OPERADOR)
    borradores = [
        _make_borrador(id=1, expediente_id=7),
        _make_borrador(id=2, expediente_id=7, tipo="proyecto_auto_vista_apelacion"),
    ]
    _override_listar_uc(borradores)

    resp = client.get("/borradores/?expediente_id=7")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == 1
    assert body[1]["tipo"] == "proyecto_auto_vista_apelacion"


def test_listar_borradores_sin_exp_invalido_422(client: TestClient) -> None:
    """Listar sin expediente_id -> 422 (Query required)."""
    _override_current_user(OPERADOR)
    _override_listar_uc([])

    resp = client.get("/borradores/")
    assert resp.status_code == 422


# ===== GET /borradores/{id} (obtener) ===============================


def test_obtener_borrador_200(client: TestClient) -> None:
    """Obtener un borrador del usuario -> 200."""
    _override_current_user(OPERADOR)
    borrador = _make_borrador(id=5, propietario_id=2, contenido="texto", estado="borrador")
    _override_obtener_uc(borrador=borrador)

    resp = client.get("/borradores/5")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 5


def test_obtener_borrador_no_existe_404(client: TestClient) -> None:
    """Obtener borrador inexistente -> 404."""
    _override_current_user(OPERADOR)
    _override_obtener_uc(error=ValueError("no encontrado"))

    resp = client.get("/borradores/999")

    assert resp.status_code == 404
    assert "no encontrado" in resp.json()["detail"].lower()


def test_obtener_borrador_ajeno_403(client: TestClient) -> None:
    """Obtener borrador ajeno en estado 'borrador' -> 403 Regla 7."""
    _override_current_user(OPERADOR)
    _override_obtener_uc(error=BorradorNoPropioError("no es propietario"))

    resp = client.get("/borradores/77")

    assert resp.status_code == 403
    assert "propietario" in resp.json()["detail"].lower()


def test_obtener_borrador_publicado_ajeno_200(client: TestClient) -> None:
    """Borrador publicado lo ve cualquiera (no raise BorradorNoPropioError)."""
    _override_current_user(OPERADOR)
    borrador = _make_borrador(id=11, propietario_id=99, estado="publicado", contenido="publicado")
    _override_obtener_uc(borrador=borrador)

    resp = client.get("/borradores/11")

    assert resp.status_code == 200
    assert resp.json()["estado"] == "publicado"


def test_obtener_borrador_publicado_supervisor_200(client: TestClient) -> None:
    """Supervisor puede ver borradores publicados (require_consulta_user)."""
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador(id=12, propietario_id=2, estado="publicado", contenido="vista")
    _override_obtener_uc(borrador=borrador)

    resp = client.get("/borradores/12")

    assert resp.status_code == 200
    assert resp.json()["estado"] == "publicado"


def test_export_borrador_docx_200(client: TestClient) -> None:
    """Exportar borrador publicado a .docx -> 200 con body de Word."""
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador(
        id=13,
        propietario_id=2,
        estado="publicado",
        tipo="auto_vista_consulta",
        contenido="# Auto de Vista\n\nVista al expediente.",
    )
    _override_obtener_uc(borrador=borrador)

    resp = client.get("/borradores/13/export")

    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "borrador_13" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"PK")


# ===== DELETE /borradores/{id} (soft delete CRITICAL #3) =============


def _override_audit_repo() -> MagicMock:
    fake = MagicMock()
    fake.registrar = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: fake
    return fake


def _override_borrador_repo_eliminar(resultado: bool) -> MagicMock:
    repo = MagicMock()
    repo.eliminar_soft = AsyncMock(return_value=resultado)
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    return repo


def test_eliminar_borrador_204(client: TestClient) -> None:
    """DELETE /borradores/{id}: 204 soft delete (Regla 7 propietario)."""
    _override_current_user(OPERADOR)
    repo = _override_borrador_repo_eliminar(resultado=True)
    _override_audit_repo()

    resp = client.delete("/borradores/77")

    assert resp.status_code == 204
    repo.eliminar_soft.assert_awaited_once_with(borrador_id=77, propietario_id=OPERADOR.id)


def test_eliminar_borrador_ajeno_404(client: TestClient) -> None:
    """Regla 7: borrador ajeno o inexistente -> 404 (sin revelar cual)."""
    _override_current_user(OPERADOR)
    _override_borrador_repo_eliminar(resultado=False)
    _override_audit_repo()

    resp = client.delete("/borradores/999")

    assert resp.status_code == 404


def test_eliminar_borrador_requiere_auth(client: TestClient) -> None:
    """Sin token valido -> 401."""
    _override_current_user(None)

    resp = client.delete("/borradores/1")

    assert resp.status_code == 401
