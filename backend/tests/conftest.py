"""pytest configuration for backend tests."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import pytest

# Añadir src/ al path para que imports funcionen
ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Precarga del modelo de layout de pymupdf4llm a nivel sesion: su import
# lazy (file_extractor.py) activa un analizador ONNX que tarda >5s en el
# worktree frio del gate y reventaba el timeout por-test colgando la
# suite (runs 01M0QV27Q8 / 01M0RNPNKE). Fuera del alcance de
# pytest-timeout, el costo se paga una sola vez al inicio.
with contextlib.suppress(ImportError):
    import pymupdf4llm  # noqa: F401

# Exponer factories en el namespace de tests via `from tests._factories import ...`
sys.path.insert(0, str(Path(__file__).parent))

# Valores minimos de env para que Settings() no falle en collection time.
# Sprint 3 fail-fast en config.py: sin RERANKER_BASE_URL el boot lanza
# RuntimeError. CI setea las variables reales; local de tests usa estas.
os.environ.setdefault("RERANKER_BASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("RERANKER_MODEL", "bge-reranker-v2-m3")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")


@pytest.fixture(autouse=True)
def _reset_factories() -> None:
    """Reset de estado entre tests.

    Hoy las factories de `tests/_factories/_factories.py` son stateless
    (cada `make_X(**overrides)` crea una nueva instancia), asi que este
    reset es un punto de extension: si en el futuro alguna factory
    accumula estado (caches, secuencias), el teardown se hace aca y un
    test nunca contamina a otro.

    Mas info: memoria Engram, topic_key
    `architecture/plan-red-de-seguridad-calidad-fundamentacional`.
    """
    yield


@pytest.fixture(autouse=True)
def _segmentadores_siempre_registrados() -> None:
    """Garantiza segmentadores reales registrados antes de cada test.

    `test_registro.py` llama `SegmentadorRegistry.limpiar()` (vacia el
    singleton global) y registra segmentadores dummy. Si corre antes que
    `test_detector_patrones.py` en la misma sesion, el detector no
    encuentra CPPM/CPM/CPE/etc. Este fixture re-registra los segmentadores
    reales si el registro quedo vacio o solo con dummies.
    """
    from src.domain.services.segmentacion.cpe import SegmentadorCPE
    from src.domain.services.segmentacion.cpm import SegmentadorCPM
    from src.domain.services.segmentacion.cppm import SegmentadorCPPM
    from src.domain.services.segmentacion.ley1970 import (
        SegmentadorLey1970Cp,
        SegmentadorLey1970Cpp,
    )
    from src.domain.services.segmentacion.lofa import SegmentadorLOFA
    from src.domain.services.segmentacion.lojm import SegmentadorLOJM
    from src.domain.services.segmentacion.registro import SegmentadorRegistry

    reales: dict[str, type] = {
        "CPPM": SegmentadorCPPM,
        "CPE": SegmentadorCPE,
        "CPM": SegmentadorCPM,
        "LOJM": SegmentadorLOJM,
        "LOFA": SegmentadorLOFA,
        "CP": SegmentadorLey1970Cp,
        "CPP": SegmentadorLey1970Cpp,
    }
    if not set(SegmentadorRegistry.disponibles()).issuperset(set(reales)):
        # test_registro vacio el singleton y registro dummies: restaurar.
        SegmentadorRegistry.limpiar()
        for abrev, cls in reales.items():
            SegmentadorRegistry.registrar(abrev, cls)
    yield


@pytest.fixture(autouse=True)
def _permisos_por_default_en_routers():
    """(Obsoleto) ver install_permiso_repo_override — se invoca por fixture client."""
    yield


def install_permiso_repo_override(app) -> None:
    """Instala el override de get_permiso_repo_dep en un TestClient de app.

    Los guards migrados a require_permiso dependen de get_permiso_repo_dep.
    En tests de routers (TestClient) se overriddea get_current_user con
    ADMIN/OPERADOR/etc. y el fixture `client` hace dependency_overrides.clear(),
    así que este override debe instalarse DESPUÉS del clear (no un autouse).

    El fake devuelve el catálogo completo con overrides vacíos, así el guard
    resuelve los DEFAULTS del rol del usuario overriddeado — comportamiento
    idéntico a los guards de rol previos (require_admin/consulta_user/...).
    """
    from src.adapters.http import dependencies as deps
    from src.domain.entities.permiso import TODAS_LAS_CLAVES, Modulo, PermisoCRUD

    class _FakePermisoRepo:
        def __init__(self) -> None:
            self.modulos = [
                Modulo(
                    clave=clave,
                    nombre=clave,
                    descripcion="",
                    ruta=f"/{clave}",
                    orden=i,
                    activo=True,
                )
                for i, clave in enumerate(sorted(TODAS_LAS_CLAVES))
            ]

        async def listar_modulos(self) -> list[Modulo]:
            return self.modulos

        async def get_permisos_usuario(self, usuario_id: int) -> dict[str, PermisoCRUD]:
            return {}

        async def actualizar_modulo(self, clave: str, **campos) -> Modulo:
            raise NotImplementedError

        async def reemplazar_permisos_usuario(
            self, usuario_id: int, permisos: dict[str, PermisoCRUD]
        ) -> None:
            raise NotImplementedError

    app.dependency_overrides[deps.get_permiso_repo_dep] = lambda: _FakePermisoRepo()

    # Los endpoints de borrador resuelven el autor (nombre+cargo) via
    # get_auth_repo. Sin este override caerian a la BD real de test.
    class _FakeAuthRepo:
        def __init__(self) -> None:
            self._por_id: dict[int, object] = {}

        async def get_by_id(self, usuario_id: int):
            return self._por_id.get(usuario_id)

    app.dependency_overrides[deps.get_auth_repo] = lambda: _FakeAuthRepo()

    # Ningun test de router debe tocar PG via audit_log: los endpoints
    # sensitivos (R6) awaitan registrar_auditoria en su happy path y el
    # await contra la BD real cuelga el portal anyio del TestClient.
    # Los tests que asertan auditoria instalan su propio fake DESPUES de
    # este override y lo reemplazan.
    class _FakeAuditLogRepo:
        def __init__(self) -> None:
            self.registros: list[object] = []

        async def registrar(self, registro: object) -> None:
            self.registros.append(registro)

        async def listar(
            self,
            accion: str | None = None,
            limit: int = 50,
            offset: int = 0,
        ) -> list[object]:
            recientes = list(reversed(self.registros))
            if accion is not None:
                recientes = [r for r in recientes if getattr(r, "accion", None) == accion]
            return recientes[offset : offset + limit]

    app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: _FakeAuditLogRepo()
