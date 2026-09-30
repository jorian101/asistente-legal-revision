"""Tests HTTP del router /expedientes (Sprint 4 Fase 6).

TDD con TestClient + dependency_overrides. Sin DB, sin PyMuPDF real.

Cobertura:
- POST /expedientes/ — 201 ok (supervisor), 409 duplicado, 403 operador
- GET  /expedientes/ — 200 lista propia
- POST /expedientes/{id}/obras — 201 ok, 422 validacion, 422 extraccion
- POST /expedientes/{id}/obras/{obra}/publicar — 200 ok, 403 no propietario
- GET  /expedientes/{id}/historial — 200, 404 expediente inexistente
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.ports.text_extractor import ExtractionResult, TextExtractor
from src.domain.entities.expediente import Expediente
from src.domain.entities.obra import Obra
from src.domain.entities.usuario import Usuario
from src.domain.services.validador_upload import ValidadorUpload
from src.main import app as fastapi_app
from tests._factories import make_supervisor, make_usuario

# --- Fakes (reutilizan definiciones del test_use_cases pero in-memory) ---


class _FakeExpedienteRepo:
    def __init__(self, existentes: list[Expediente] | None = None) -> None:
        self._por_id: dict[int, Expediente] = {}
        self._por_numero: dict[str, Expediente] = {}
        self._next_id = 1
        for e in existentes or []:
            e.id = self._next_id
            e.created_at = datetime.now(UTC)
            self._por_id[self._next_id] = e
            self._por_numero[e.numero_caso] = e
            self._next_id += 1

    async def guardar(self, expediente: Expediente) -> Expediente:
        expediente.id = self._next_id
        expediente.created_at = datetime.now(UTC)
        self._por_id[self._next_id] = expediente
        self._por_numero[expediente.numero_caso] = expediente
        self._next_id += 1
        return expediente

    async def obtener(self, expediente_id: int) -> Expediente | None:
        return self._por_id.get(expediente_id)

    async def obtener_por_numero_caso(self, numero_caso: str) -> Expediente | None:
        return self._por_numero.get(numero_caso)

    async def listar_por_usuario(
        self,
        usuario_id: int,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        items = [e for e in self._por_id.values() if e.abierto_por == usuario_id]
        if estado is not None:
            items = [e for e in items if e.estado == estado]
        total = len(items)
        start = (pagina - 1) * por_pagina
        return items[start : start + por_pagina], total

    async def listar_todos(
        self,
        *,
        incluir_archivados: bool = False,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        items = list(self._por_id.values())
        if not incluir_archivados:
            items = [e for e in items if e.estado == "activo"]
        if estado is not None:
            items = [e for e in items if e.estado == estado]
        total = len(items)
        start = (pagina - 1) * por_pagina
        return items[start : start + por_pagina], total

    async def actualizar_estado(self, expediente_id: int, estado: str) -> Expediente | None:
        if expediente_id not in self._por_id:
            return None
        self._por_id[expediente_id].estado = estado
        return self._por_id[expediente_id]

    async def actualizar(
        self,
        expediente_id: int,
        *,
        numero_caso: str | None = None,
        procesado_nombre: str | None = None,
        delito: str | None = None,
        tribunal_origen: str | None = None,
        tipo_proceso: str | None = None,
    ) -> Expediente | None:
        exp = self._por_id.get(expediente_id)
        if exp is None:
            return None
        if numero_caso is not None:
            exp.numero_caso = numero_caso
        if procesado_nombre is not None:
            exp.procesado_nombre = procesado_nombre
        if delito is not None:
            exp.delito = delito
        if tribunal_origen is not None:
            exp.tribunal_origen = tribunal_origen
        if tipo_proceso is not None:
            exp.tipo_proceso = tipo_proceso
        return exp


class _FakeObraRepo:
    def __init__(self, existentes: list[Obra] | None = None) -> None:
        self._por_id: dict[int, Obra] = {}
        self._next_id = 1
        for o in existentes or []:
            o.id = self._next_id
            o.created_at = datetime.now(UTC)
            self._por_id[self._next_id] = o
            self._next_id += 1

    async def guardar(self, obra: Obra) -> Obra:
        obra.id = self._next_id
        obra.created_at = datetime.now(UTC)
        self._por_id[self._next_id] = obra
        self._next_id += 1
        return obra

    async def obtener(self, obra_id: int, usuario_id: int) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        if o.propietario_id == usuario_id or o.estado_visibilidad == "publicado":
            return o
        return None

    async def listar_por_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        solo_propias: bool = False,
    ) -> list[Obra]:
        out: list[Obra] = []
        for o in self._por_id.values():
            if o.expediente_id != expediente_id:
                continue
            if solo_propias:
                if o.propietario_id != usuario_id:
                    continue
            else:
                if o.propietario_id != usuario_id and o.estado_visibilidad != "publicado":
                    continue
            out.append(o)
        return out

    async def publicar(self, obra_id: int, propietario_id: int) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None or o.propietario_id != propietario_id:
            return None
        o.estado_visibilidad = "publicado"
        return o

    async def actualizar_estado_procesamiento(self, obra_id: int, estado: str) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        o.estado_procesamiento = estado  # type: ignore[assignment]
        return o

    async def obtener_por_ids(self, obra_ids: list[int], usuario_id: int) -> dict[int, Obra]:
        return {
            i: o
            for i, o in self._por_id.items()
            if i in obra_ids and o.propietario_id == usuario_id
        }

    async def eliminar(self, obra_id: int) -> bool:
        return self._por_id.pop(obra_id, None) is not None

    async def marcar_promocion(
        self, obra_id: int, estado: str, motivo: str | None = None
    ) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        o.estado_validacion = estado
        return o

    async def promover_a_jurisprudencia(self, obra_id: int) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        o.tipo_documento = "jurisprudencia"  # type: ignore[assignment]
        o.estado_visibilidad = "global"
        o.estado_validacion = "promovida"
        return o

    async def listar_promociones_pendientes(self) -> list[Obra]:
        return [o for o in self._por_id.values() if o.estado_validacion == "promocion_pendiente"]


class _ExtractorOk(TextExtractor):
    @override
    async def extract(self, file_path: Path, pages: list[int] | None = None) -> ExtractionResult:
        return ExtractionResult(
            full_text="texto prueba",
            blocks=[],
            pages_count=1,
            extracted_pages=[1],
            metadata={},
        )

    @override
    async def extract_pages(self, file_path: Path, pages: list[int]) -> ExtractionResult:
        return await self.extract(file_path, pages)


class _ExtractorFail(TextExtractor):
    @override
    async def extract(self, file_path: Path, pages: list[int] | None = None) -> ExtractionResult:
        raise RuntimeError("pdf malo")

    @override
    async def extract_pages(self, file_path: Path, pages: list[int]) -> ExtractionResult:
        return await self.extract(file_path, pages)


class _ValidadorAcepta(ValidadorUpload):
    @override
    def validar(self, filename: str, content_type: str, data: bytes) -> None:
        return None


class _ValidadorRechaza(ValidadorUpload):
    @override
    def validar(self, filename: str, content_type: str, data: bytes) -> None:
        from src.domain.services.validador_upload import UploadInvalidoError

        raise UploadInvalidoError("rechazado test")


class _Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index)] for index, _ in enumerate(texts)]

    async def close(self) -> None:
        return None


class _FragmentoRepo:
    async def delete_by_obra(self, obra_id: int) -> int:
        return 0

    async def save_many(self, fragmentos: list[object]) -> list[object]:
        return fragmentos


class _VectorRepo:
    async def delete_by_obra(self, obra_id: int) -> None:
        return None

    async def upsert_corpus(self, points: list[dict]) -> None:
        return None

    async def actualizar_payload_obra(self, obra_id: int, payload: dict) -> None:
        return None


# --- Fixtures ---


@pytest.fixture
def supervisor() -> Usuario:
    # id explicito: el fake repo NO asigna id al Usuario (solo a Expediente/Obra).
    # Sin esto los tests fallan por propietario_id=None == None → siempre iguales.
    return make_supervisor(id=2)


@pytest.fixture
def operador() -> Usuario:
    return make_usuario(id=3)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    import src.routers.expedientes as mod

    orig_settings = mod.get_settings
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()
    mod.get_settings = orig_settings  # type: ignore[assignment]


def _override_auth(usuario: Usuario, *, auth_only: bool = False) -> None:
    """Pone `usuario` como current_user via override de get_current_user.

    Por defecto tambien bypasea require_consulta_user y require_supervisor
    (utiles para tests de happy path). Si queres que se aplique la policy
    de rol real (ej. test_403), usar auth_only=True: solo override
    get_current_user, las require_* siguen su logic de Validacion de rol.
    """
    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    if not auth_only:
        fastapi_app.dependency_overrides[deps.require_consulta_user] = lambda: usuario
        fastapi_app.dependency_overrides[deps.require_supervisor] = lambda: usuario


def _override_repos(
    expediente_repo: _FakeExpedienteRepo,
    obra_repo: _FakeObraRepo,
    extractor: TextExtractor | None = None,
    validador: ValidadorUpload | None = None,
    tmp_path: Path | None = None,
) -> None:
    """Override sobre los callables de dependency injection.

    NO tocar los alias Annotated[X, Depends(...)] — eso no funciona.
    Override sobre el callable subyacente (get_expediente_repo_dep, etc).
    """
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: expediente_repo
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo
    fastapi_app.dependency_overrides[deps.get_fragmento_repo] = lambda: _FragmentoRepo()
    fastapi_app.dependency_overrides[deps.get_embedder] = lambda: _Embedder()
    fastapi_app.dependency_overrides[deps.get_vector_repo] = lambda: _VectorRepo()
    if extractor is not None:
        fastapi_app.dependency_overrides[deps.get_text_extractor] = lambda: extractor
    if validador is not None:
        fastapi_app.dependency_overrides[deps.get_validador] = lambda: validador
    if tmp_path is not None:
        _override_storage(tmp_path)


def _override_storage(tmp_path: Path) -> None:
    """Mock get_settings().upload_dir -> tmp_path (sin tocar BD)."""
    import src.routers.expedientes as mod

    class _FakeSettings:
        upload_dir = str(tmp_path)

    mod.get_settings = lambda: _FakeSettings()  # type: ignore[assignment]


PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ncontenido"


# --- Tests POST /expedientes/ ---


class TestAbrirExpedienteRouter:
    def test_201_supervisor_abre_expediente(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        repo = _FakeExpedienteRepo()
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.post(
            "/expedientes/",
            json={
                "numero_caso": "TSJM-C-2024-001",
                "tipo_proceso": "consulta",
                "tribunal_origen": "TSJM",
                "procesado_nombre": "Juan Perez",
                "delito": "Desobedencia",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["expediente_id"] == 1
        assert data["numero_caso"] == "TSJM-C-2024-001"
        assert data["estado"] == "activo"

    def test_409_numero_caso_duplicado(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        existente = make_expediente(numero_caso="DUP-001", abierto_por=2)
        repo = _FakeExpedienteRepo(existentes=[existente])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.post(
            "/expedientes/",
            json={
                "numero_caso": "DUP-001",
                "tipo_proceso": "consulta",
                "tribunal_origen": "TSJM",
                "procesado_nombre": "X",
                "delito": "Y",
            },
        )

        assert resp.status_code == 409

    def test_403_operador_no_puede_abrir(self, client, operador, tmp_path):
        _override_auth(operador, auth_only=True)  # aplica policy de require_supervisor
        _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.post(
            "/expedientes/",
            json={
                "numero_caso": "TSJM-C-2024-002",
                "tipo_proceso": "consulta",
                "tribunal_origen": "TSJM",
                "procesado_nombre": "X",
                "delito": "Y",
            },
        )

        # require_supervisor debe rechazar. Si la app define policy por rol,
        # deberìa devolver 403.
        assert resp.status_code in (403, 401)


# --- Tests GET /expedientes/ ---


class TestListarExpedientesRouter:
    def test_200_lista_propia(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        existente = make_expediente(numero_caso="A-001", abierto_por=supervisor.id)
        repo = _FakeExpedienteRepo(existentes=[existente])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.get("/expedientes/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["numero_caso"] == "A-001"

    def test_operador_ve_expedientes_activos_de_otro_supervisor(
        self, client, supervisor, operador, tmp_path
    ):
        """Plan: expedientes compartidos. El operador ve los expedientes activos
        que el supervisor abrió (fix #322 restaurado)."""
        from tests._factories import make_expediente

        _override_auth(operador, auth_only=True)
        exp_sup = make_expediente(numero_caso="SUP-001", abierto_por=supervisor.id)
        exp_arch = make_expediente(
            numero_caso="ARCH-001", abierto_por=supervisor.id, estado="archivado"
        )
        repo = _FakeExpedienteRepo(existentes=[exp_sup, exp_arch])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.get("/expedientes/")

        assert resp.status_code == 200
        data = resp.json()
        casos = [i["numero_caso"] for i in data["items"]]
        assert "SUP-001" in casos
        assert "ARCH-001" not in casos  # archivado NO visible para operador

    def test_supervisor_ve_expedientes_archivados(self, client, supervisor, tmp_path):
        """El supervisor ve todos (activos + archivados)."""
        from tests._factories import make_expediente

        _override_auth(supervisor, auth_only=True)
        exp_arch = make_expediente(
            numero_caso="ARCH-002", abierto_por=supervisor.id, estado="archivado"
        )
        repo = _FakeExpedienteRepo(existentes=[exp_arch])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.get("/expedientes/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["numero_caso"] == "ARCH-002"


# --- Tests POST /expedientes/{id}/obras ---


class TestCargarObraRouter:
    def test_201_carga_exitosa(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="X-001", abierto_por=supervisor.id)
        exp_repo = _FakeExpedienteRepo(existentes=[exp])
        obra_repo = _FakeObraRepo()
        _override_repos(
            exp_repo,
            obra_repo,
            extractor=_ExtractorOk(),
            validador=_ValidadorAcepta(),
            tmp_path=tmp_path,
        )
        audit = _override_audit_repo()

        resp = client.post(
            f"/expedientes/{exp.id}/obras",
            files={"file": ("sentencia.pdf", PDF_BYTES, "application/pdf")},
            data={"tipo_documento": "sentencia"},
        )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["obra_id"] == 1
        # Piezas de entrada (taxonomía A) nacen publicadas — commit 99b2c8d.
        assert data["estado_visibilidad"] == "publicado"
        # R6: la carga de obrados alimenta el RAG del caso -> auditada.
        assert [c.args[0].accion for c in audit.registrar.await_args_list] == ["cargar_obra"]

    def test_422_validacion_fallida(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="X-002", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            extractor=_ExtractorOk(),
            validador=_ValidadorRechaza(),
            tmp_path=tmp_path,
        )

        resp = client.post(
            f"/expedientes/{exp.id}/obras",
            files={"file": ("mal.exe", b"MZ", "application/x-msdownload")},
            data={"tipo_documento": "otro"},
        )

        assert resp.status_code == 422

    @pytest.mark.parametrize("tipo", ["doctrina", "criterio", "jurisprudencia", "ejemplo"])
    def test_422_los_tipos_que_no_son_obrados_no_se_cargan_como_obrado(
        self, client, supervisor, tmp_path, tipo
    ):
        """Doctrina son libros, jurisprudencia se promueve y el criterio es instruccion:
        ninguno se sube por el endpoint de obrados."""
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="X-003", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            extractor=_ExtractorOk(),
            validador=_ValidadorAcepta(),
            tmp_path=tmp_path,
        )

        resp = client.post(
            f"/expedientes/{exp.id}/obras",
            files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
            data={"tipo_documento": tipo},
        )

        assert resp.status_code == 422

    def test_422_extraccion_fallida(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="X-003", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            extractor=_ExtractorFail(),
            validador=_ValidadorAcepta(),
            tmp_path=tmp_path,
        )

        resp = client.post(
            f"/expedientes/{exp.id}/obras",
            files={"file": ("roto.pdf", PDF_BYTES, "application/pdf")},
            data={"tipo_documento": "sentencia"},
        )

        assert resp.status_code == 422

    def test_404_expediente_inexistente(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        _override_repos(
            _FakeExpedienteRepo(),  # vacio
            _FakeObraRepo(),
            extractor=_ExtractorOk(),
            validador=_ValidadorAcepta(),
            tmp_path=tmp_path,
        )

        resp = client.post(
            "/expedientes/9999/obras",
            files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
            data={"tipo_documento": "otro"},
        )

        assert resp.status_code == 404


# --- Tests POST /expedientes/{id}/obras/{obra}/publicar ---


class TestPublicarObraRouter:
    def test_200_publicar_propietario(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="P-001", abierto_por=supervisor.id)
        obra = Obra(
            id=None,
            expediente_id=1,
            propietario_id=supervisor.id,
            tipo_documento="sentencia",
            nombre_archivo="x.pdf",
            contenido_texto="",
        )
        obra_repo = _FakeObraRepo(existentes=[obra])
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.post("/expedientes/1/obras/1/publicar")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["estado_visibilidad"] == "publicado"

    def test_403_no_propietario(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente, make_usuario

        otro = make_usuario(id=5, carnet="5555555")  # id explicito
        _override_auth(supervisor)  # supervisor intenta publicar
        exp = make_expediente(numero_caso="P-002", abierto_por=otro.id)
        # obra propiedad del otro usuario (NO del supervisor)
        obra = Obra(
            id=None,
            expediente_id=1,
            propietario_id=otro.id,  # 5 != 2 (supervisor.id)
            tipo_documento="sentencia",
            nombre_archivo="x.pdf",
            contenido_texto="",
        )
        obra_repo = _FakeObraRepo(existentes=[obra])
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.post("/expedientes/1/obras/1/publicar")

        assert resp.status_code == 403


# --- Tests GET /expedientes/{id}/historial ---


class TestHistorialRouter:
    def test_200_lista_obras_visibles(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente, make_usuario

        otro = make_usuario(id=4, carnet="4444444")  # id explicito
        _override_auth(supervisor)  # id=2 (supervisor por defecto)
        exp = make_expediente(numero_caso="H-001", abierto_por=supervisor.id)
        obras = [
            Obra(  # propia
                id=None,
                expediente_id=1,
                propietario_id=supervisor.id,
                tipo_documento="sentencia",
                nombre_archivo="propia.pdf",
                contenido_texto="",
            ),
            Obra(  # ajena publicada -> visible
                id=None,
                expediente_id=1,
                propietario_id=otro.id,
                tipo_documento="sentencia",
                nombre_archivo="pub.pdf",
                contenido_texto="",
                estado_visibilidad="publicado",
            ),
            Obra(  # ajena privada -> NO visible (Regla 5)
                id=None,
                expediente_id=1,
                propietario_id=otro.id,
                tipo_documento="sentencia",
                nombre_archivo="priv.pdf",
                contenido_texto="",
            ),
        ]
        obra_repo = _FakeObraRepo(existentes=obras)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.get("/expedientes/1/historial")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 2  # propia + publicada
        nombres = [o["nombre_archivo"] for o in data["obras"]]
        assert "propia.pdf" in nombres
        assert "pub.pdf" in nombres
        assert "priv.pdf" not in nombres

    def test_404_expediente_inexistente(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        _override_repos(
            _FakeExpedienteRepo(),  # vacio
            _FakeObraRepo(),
            tmp_path=tmp_path,
        )

        resp = client.get("/expedientes/9999/historial")

        assert resp.status_code == 404


def _override_audit_repo() -> MagicMock:
    fake = MagicMock()
    fake.registrar = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: fake
    return fake


def test_eliminar_expediente_204_archiva(client: TestClient, supervisor, tmp_path) -> None:
    """CRITICAL #3: DELETE /expedientes/{id} -> 204 (estado archivado)."""
    from src.domain.entities.expediente import Expediente

    repo = _FakeExpedienteRepo()
    repo.actualizar_estado = AsyncMock(
        return_value=Expediente(
            id=5,
            numero_caso="TSJM-2024-005",
            tipo_proceso="consulta",
            tribunal_origen="TM1",
            procesado_nombre="N",
            delito="D",
            abierto_por=supervisor.id,
            estado="archivado",
        )
    )
    _override_auth(supervisor)
    _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)
    _override_audit_repo()

    resp = client.delete("/expedientes/5")

    assert resp.status_code == 204
    repo.actualizar_estado.assert_awaited_once_with(5, "archivado")


def test_eliminar_expediente_404(client: TestClient, supervisor, tmp_path) -> None:
    """Expediente inexistente -> 404."""
    repo = _FakeExpedienteRepo()
    repo.actualizar_estado = AsyncMock(return_value=None)
    _override_auth(supervisor)
    _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)
    _override_audit_repo()

    resp = client.delete("/expedientes/999")

    assert resp.status_code == 404


def test_eliminar_expediente_403_no_supervisor(client: TestClient, operador, tmp_path) -> None:
    """require_supervisor: operador juridico -> 403."""
    _override_auth(operador, auth_only=True)
    _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(), tmp_path=tmp_path)

    resp = client.delete("/expedientes/5")

    assert resp.status_code == 403


# --- Tests PATCH /expedientes/{id}/estado (toggle) ---


class TestCambiarEstadoRouter:
    def test_200_toggle_activo_a_archivado(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="E-001", abierto_por=supervisor.id)
        repo = _FakeExpedienteRepo(existentes=[exp])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)
        _override_audit_repo()

        resp = client.patch("/expedientes/1/estado", json={"estado": "archivado"})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["estado"] == "archivado"
        assert data["numero_caso"] == "E-001"

    def test_200_toggle_archivado_a_activo(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="E-002", abierto_por=supervisor.id, estado="archivado")
        repo = _FakeExpedienteRepo(existentes=[exp])
        _override_repos(repo, _FakeObraRepo(), tmp_path=tmp_path)
        _override_audit_repo()

        resp = client.patch("/expedientes/1/estado", json={"estado": "activo"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["estado"] == "activo"

    def test_422_estado_invalido(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="E-003", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            tmp_path=tmp_path,
        )

        resp = client.patch("/expedientes/1/estado", json={"estado": "borrado"})

        assert resp.status_code == 422

    def test_404_expediente_inexistente(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        _override_repos(
            _FakeExpedienteRepo(),
            _FakeObraRepo(),
            tmp_path=tmp_path,
        )

        resp = client.patch("/expedientes/9999/estado", json={"estado": "archivado"})

        assert resp.status_code == 404

    def test_403_operador_no_puede_cambiar_estado(self, client, operador, tmp_path):
        _override_auth(operador, auth_only=True)
        _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.patch("/expedientes/1/estado", json={"estado": "archivado"})

        assert resp.status_code == 403


# --- Tests PATCH /expedientes/{id} (edicion) ---


class TestEditarExpedienteRouter:
    def test_200_edicion_parcial(self, client, supervisor, tmp_path):
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="ED-001", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            tmp_path=tmp_path,
        )
        _override_audit_repo()

        resp = client.patch("/expedientes/1", json={"procesado_nombre": "Nuevo Nombre"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["procesado_nombre"] == "Nuevo Nombre"

    def test_200_edicion_con_string_vacio_no_rompe(self, client, supervisor, tmp_path):
        """El backend tolera '' en campos opcionales (no los actualiza)."""
        from tests._factories import make_expediente

        _override_auth(supervisor)
        exp = make_expediente(numero_caso="ED-002", abierto_por=supervisor.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            tmp_path=tmp_path,
        )
        _override_audit_repo()

        resp = client.patch(
            "/expedientes/1",
            json={
                "numero_caso": "ED-002",
                "procesado_nombre": "",
                "delito": "",
                "tribunal_origen": "",
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        # El numero_caso se conserva, los vacios no se pisaron.
        assert data["numero_caso"] == "ED-002"

    def test_404_expediente_inexistente(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.patch("/expedientes/9999", json={"delito": "X"})

        assert resp.status_code == 404


# --- F1: módulo 'obras' — operador trabaja archivos sin editar expediente ---


class TestPermisosObrasOperador:
    """El módulo 'obras' desacopla las operaciones de archivos del guard
    'expedientes.actualizar' (bug introducido por commit 0af2a54): el
    operador carga/publica/elimina SUS obras pero no edita el expediente."""

    def test_201_operador_carga_obra(self, client, operador, tmp_path):
        from tests._factories import make_expediente

        _override_auth(operador)
        exp = make_expediente(numero_caso="OB-001", abierto_por=operador.id)
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(),
            extractor=_ExtractorOk(),
            validador=_ValidadorAcepta(),
            tmp_path=tmp_path,
        )

        resp = client.post(
            f"/expedientes/{exp.id}/obras",
            files={"file": ("sentencia.pdf", PDF_BYTES, "application/pdf")},
            data={"tipo_documento": "sentencia"},
        )

        assert resp.status_code == 201, resp.text

    def test_200_operador_publica_su_obra(self, client, operador, tmp_path):
        from tests._factories import make_expediente

        _override_auth(operador)
        exp = make_expediente(numero_caso="OB-002", abierto_por=operador.id)
        obra = Obra(
            id=None,
            expediente_id=1,
            propietario_id=operador.id,
            tipo_documento="sentencia",
            nombre_archivo="x.pdf",
            contenido_texto="",
        )
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            _FakeObraRepo(existentes=[obra]),
            tmp_path=tmp_path,
        )

        resp = client.post("/expedientes/1/obras/1/publicar")

        assert resp.status_code == 200, resp.text

    def test_200_operador_elimina_su_obra(self, client, operador, tmp_path):
        from tests._factories import make_expediente

        _override_auth(operador)
        exp = make_expediente(numero_caso="OB-003", abierto_por=operador.id)
        obra = Obra(
            id=None,
            expediente_id=1,
            propietario_id=operador.id,
            tipo_documento="sentencia",
            nombre_archivo="x.pdf",
            contenido_texto="",
        )
        obra_repo = _FakeObraRepo(existentes=[obra])
        _override_repos(
            _FakeExpedienteRepo(existentes=[exp]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.delete("/expedientes/1/obras/1")

        assert resp.status_code == 204, resp.text
        assert 1 not in obra_repo._por_id

    def test_403_operador_no_edita_expediente(self, client, operador):
        from tests._factories import make_expediente

        _override_auth(operador)
        exp_repo = _FakeExpedienteRepo(
            existentes=[make_expediente(numero_caso="OB-004", abierto_por=operador.id)]
        )
        _override_repos(exp_repo, _FakeObraRepo())

        resp = client.patch(f"/expedientes/{exp_repo._por_id[1].id}", json={})

        assert resp.status_code == 403

    def test_403_operador_no_cambia_estado_expediente(self, client, operador):
        from tests._factories import make_expediente

        _override_auth(operador)
        exp = make_expediente(numero_caso="OB-005", abierto_por=operador.id)
        exp_repo = _FakeExpedienteRepo(existentes=[exp])
        _override_repos(exp_repo, _FakeObraRepo())

        resp = client.patch(f"/expedientes/{exp.id}/estado", json={"estado": "archivado"})

        assert resp.status_code == 403


# --- Promoción de obrados a jurisprudencia ---


def _obra_publicada(propietario_id: int, **kw) -> Obra:
    return Obra(
        id=None,
        expediente_id=1,
        propietario_id=propietario_id,
        tipo_documento="sentencia",
        nombre_archivo="x.pdf",
        contenido_texto="",
        estado_visibilidad="publicado",
        **kw,
    )


class TestPromocionRouter:
    def test_el_operador_propone_su_obrado(self, client, operador, tmp_path):
        from tests._factories import make_expediente

        _override_auth(operador)
        obra_repo = _FakeObraRepo(existentes=[_obra_publicada(operador.id)])
        _override_repos(
            _FakeExpedienteRepo(existentes=[make_expediente(numero_caso="P-9")]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.post("/expedientes/1/obras/1/proponer-promocion")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "obra_id": 1,
            "tipo_documento": "sentencia",
            "estado_validacion": "promocion_pendiente",
        }

    def test_409_si_no_esta_publicado(self, client, operador, tmp_path):
        _override_auth(operador)
        obra = _obra_publicada(operador.id)
        obra.estado_visibilidad = "privado"
        _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(existentes=[obra]), tmp_path=tmp_path)

        resp = client.post("/expedientes/1/obras/1/proponer-promocion")

        assert resp.status_code in (404, 409)

    def test_el_supervisor_aprueba_y_la_obra_es_jurisprudencia(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        obra_repo = _FakeObraRepo(
            existentes=[_obra_publicada(7, estado_validacion="promocion_pendiente")]
        )
        _override_repos(_FakeExpedienteRepo(), obra_repo, tmp_path=tmp_path)

        resp = client.post("/expedientes/1/obras/1/resolver-promocion", json={"aprobar": True})

        assert resp.status_code == 200, resp.text
        assert resp.json()["tipo_documento"] == "jurisprudencia"
        assert resp.json()["estado_validacion"] == "promovida"

    def test_rechazar_sin_motivo_es_422(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        obra_repo = _FakeObraRepo(
            existentes=[_obra_publicada(7, estado_validacion="promocion_pendiente")]
        )
        _override_repos(_FakeExpedienteRepo(), obra_repo, tmp_path=tmp_path)

        resp = client.post("/expedientes/1/obras/1/resolver-promocion", json={"aprobar": False})

        assert resp.status_code == 422

    def test_el_operador_no_puede_resolver(self, client, operador, tmp_path):
        _override_auth(operador, auth_only=True)
        _override_repos(_FakeExpedienteRepo(), _FakeObraRepo(), tmp_path=tmp_path)

        resp = client.post("/expedientes/1/obras/1/resolver-promocion", json={"aprobar": True})

        assert resp.status_code == 403

    def test_el_supervisor_lista_las_promociones_pendientes(self, client, supervisor, tmp_path):
        _override_auth(supervisor)
        obra_repo = _FakeObraRepo(
            existentes=[
                _obra_publicada(7, estado_validacion="promocion_pendiente"),
                _obra_publicada(7),
            ]
        )
        _override_repos(_FakeExpedienteRepo(), obra_repo, tmp_path=tmp_path)

        resp = client.get("/expedientes/promociones-pendientes")

        assert resp.status_code == 200, resp.text
        assert [o["obra_id"] for o in resp.json()] == [1]

    def test_el_historial_expone_el_estado_de_la_promocion(self, client, operador, tmp_path):
        from tests._factories import make_expediente

        _override_auth(operador)
        obra_repo = _FakeObraRepo(
            existentes=[_obra_publicada(operador.id, estado_validacion="promocion_pendiente")]
        )
        _override_repos(
            _FakeExpedienteRepo(existentes=[make_expediente(numero_caso="P-10")]),
            obra_repo,
            tmp_path=tmp_path,
        )

        resp = client.get("/expedientes/1/historial")

        assert resp.status_code == 200, resp.text
        assert resp.json()["obras"][0]["estado_validacion"] == "promocion_pendiente"
