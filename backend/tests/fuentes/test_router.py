"""Router /fuentes: flujo común de normas, jurisprudencia y doctrina."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.application.ports.text_extractor import ExtractionResult, TextExtractor
from src.domain.services.validador_upload import ValidadorUpload
from src.main import app as fastapi_app
from tests._factories import make_supervisor, make_usuario

LEY = "Artículo 1. (Objeto). Regula los recursos.\n\nArtículo 2. (Alcance). Aplica a todos.\n"


class _Extractor(TextExtractor):
    async def extract(self, file_path, pages=None):
        return ExtractionResult(
            full_text=LEY, blocks=[], pages_count=1, extracted_pages=[1], metadata={}
        )

    async def extract_pages(self, file_path, pages):
        return await self.extract(file_path, pages)


class _Validador(ValidadorUpload):
    def validar(self, filename, content_type, data):
        return None


def _norma(**kw):
    base = {
        "id": 1,
        "abreviatura": "LIB-A",
        "nombre": "Libro A",
        "tipo": "doctrina_libro",
        "jerarquia": "doctrina",
        "indexado": True,
        "activo": True,
        "propietario_id": 3,
        "estado_visibilidad": "privado",
        "motivo_rechazo": None,
    }
    return SimpleNamespace(**{**base, **kw})


class _NormaRepo:
    def __init__(self, normas=None):
        self.normas = list(normas or [])

    async def list_all(self):
        return self.normas

    async def get_by_id(self, i):
        return next((n for n in self.normas if n.id == i), None)

    async def get_by_abreviatura(self, a):
        return next((n for n in self.normas if n.abreviatura == a), None)

    async def save(self, norma):
        norma.id = 100 + len(self.normas)
        self.normas.append(norma)
        return norma

    async def marcar_indexada(self, norma_id, indexado_por):
        return None

    async def actualizar_visibilidad(self, norma_id, estado, motivo=None):
        n = await self.get_by_id(norma_id)
        n.estado_visibilidad = estado
        n.motivo_rechazo = motivo
        return n


class _Vector:
    def __init__(self):
        self.payloads = []

    def _collection_has_sparse(self):
        return False

    async def upsert_corpus(self, points):
        self.payloads.extend(p["payload"] for p in points)

    async def actualizar_payload_norma(self, norma_id, payload):
        self.payloads.append((norma_id, payload))


class _Embedder:
    async def embed(self, textos):
        return [[0.1] * 4 for _ in textos]

    async def close(self):
        return None


class _FragmentoRepo:
    async def save_many(self, fragmentos):
        return fragmentos

    async def asignar_padres_por_ids(self, pares):
        return None


@pytest.fixture
def operador():
    return make_usuario(id=3)


@pytest.fixture
def supervisor():
    return make_supervisor(id=2)


@pytest.fixture
def client():
    fastapi_app.dependency_overrides.clear()
    install_permiso_repo_override(fastapi_app)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def _montar(usuario, repo, *, auth_only=False):
    fastapi_app.dependency_overrides[deps.get_current_user] = lambda: usuario
    if not auth_only:
        fastapi_app.dependency_overrides[deps.require_supervisor] = lambda: usuario
    vector = _Vector()
    fastapi_app.dependency_overrides[deps.get_norma_repo] = lambda: repo
    fastapi_app.dependency_overrides[deps.get_vector_repo] = lambda: vector
    fastapi_app.dependency_overrides[deps.get_vector_repo_jurisprudencia] = lambda: vector
    fastapi_app.dependency_overrides[deps.get_vector_repo_doctrina] = lambda: vector
    fastapi_app.dependency_overrides[deps.get_embedder] = lambda: _Embedder()
    fastapi_app.dependency_overrides[deps.get_fragmento_repo] = lambda: _FragmentoRepo()
    fastapi_app.dependency_overrides[deps.get_text_extractor] = lambda: _Extractor()
    fastapi_app.dependency_overrides[deps.get_validador] = lambda: _Validador()
    fastapi_app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: MagicMock(
        registrar=AsyncMock()
    )
    return vector


def _esperar_job(client, job_id: str, timeout: float = 5.0) -> dict:
    """Pollea /jobs hasta que el trabajo deje de estar en curso."""
    limite = time.monotonic() + timeout
    cuerpo: dict = {}
    while time.monotonic() < limite:
        cuerpo = client.get(f"/jobs/{job_id}").json()
        if cuerpo["estado"] != "en_curso":
            return cuerpo
        time.sleep(0.01)
    raise AssertionError(f"el trabajo {job_id} no termino: {cuerpo}")


def test_listar_muestra_lo_global_y_lo_propio(client, operador):
    repo = _NormaRepo(
        [
            _norma(id=1, estado_visibilidad="global", propietario_id=None),
            _norma(id=2, propietario_id=3),
            _norma(id=3, propietario_id=99),
        ]
    )
    _montar(operador, repo)

    resp = client.get("/fuentes", params={"categoria": "doctrina"})

    assert resp.status_code == 200, resp.text
    assert [f["id"] for f in resp.json()] == [1, 2]
    assert resp.json()[1]["es_propia"] is True
    assert resp.json()[1]["categoria"] == "doctrina"


def test_categoria_invalida_es_422(client, operador):
    _montar(operador, _NormaRepo())

    assert client.get("/fuentes", params={"categoria": "otra"}).status_code == 422


def test_el_operador_sube_una_norma_privada(client, operador):
    repo = _NormaRepo()
    vector = _montar(operador, repo)

    resp = client.post(
        "/fuentes",
        files={"file": ("ley.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"categoria": "norma", "nombre": "Ley de recursos", "jerarquia": "supletoria"},
    )

    assert resp.status_code == 202, resp.text
    assert _esperar_job(client, resp.json()["job_id"])["estado"] == "completado"
    # La seleccion del usuario se respeta: privada y de el.
    assert repo.normas[0].propietario_id == operador.id
    assert repo.normas[0].estado_visibilidad == "privado"
    assert vector.payloads[0]["visibilidad"] == "privado"


def test_el_supervisor_sube_directo_a_global(client, supervisor):
    repo = _NormaRepo()
    _montar(supervisor, repo)

    resp = client.post(
        "/fuentes",
        files={"file": ("ley.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"categoria": "norma", "nombre": "Ley X", "jerarquia": "suprema"},
    )

    assert resp.status_code == 202, resp.text
    assert _esperar_job(client, resp.json()["job_id"])["estado"] == "completado"
    assert repo.normas[0].estado_visibilidad == "global"


def test_una_norma_sin_articulos_deja_el_trabajo_en_error(client, operador, monkeypatch):
    _montar(operador, _NormaRepo())

    class _Sin(_Extractor):
        async def extract(self, file_path, pages=None):
            return ExtractionResult(
                full_text="Sin estructura.",
                blocks=[],
                pages_count=1,
                extracted_pages=[1],
                metadata={},
            )

    fastapi_app.dependency_overrides[deps.get_text_extractor] = lambda: _Sin()

    resp = client.post(
        "/fuentes",
        files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"categoria": "norma", "nombre": "Nada", "jerarquia": "supletoria"},
    )

    # El fallo ya no es un 422 inmediato: el trabajo se encola y falla.
    assert resp.status_code == 202, resp.text
    cuerpo = _esperar_job(client, resp.json()["job_id"])
    assert cuerpo["estado"] == "error"
    assert cuerpo["error"]


def test_el_dueno_propone_y_otro_no(client, operador):
    repo = _NormaRepo([_norma(id=1, propietario_id=operador.id)])
    _montar(operador, repo)

    assert client.post("/fuentes/1/proponer").status_code == 200
    assert repo.normas[0].estado_visibilidad == "pendiente"

    repo2 = _NormaRepo([_norma(id=1, propietario_id=99)])
    _montar(operador, repo2)
    assert client.post("/fuentes/1/proponer").status_code == 403


def test_el_supervisor_aprueba_y_rechaza_con_motivo(client, supervisor):
    repo = _NormaRepo([_norma(id=1, estado_visibilidad="pendiente")])
    _montar(supervisor, repo)

    assert client.post("/fuentes/1/resolver", json={"aprobar": False}).status_code == 422
    resp = client.post("/fuentes/1/resolver", json={"aprobar": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["estado_visibilidad"] == "global"


def test_el_operador_no_puede_resolver(client, operador):
    _montar(operador, _NormaRepo([_norma(id=1, estado_visibilidad="pendiente")]), auth_only=True)

    assert client.post("/fuentes/1/resolver", json={"aprobar": True}).status_code == 403


def test_pendientes_solo_para_el_supervisor(client, supervisor):
    repo = _NormaRepo(
        [
            _norma(id=1, estado_visibilidad="pendiente", propietario_id=3),
            _norma(
                id=2, jerarquia="jurisprudencia", tipo="scp_tcp", estado_visibilidad="pendiente"
            ),
            _norma(id=3, estado_visibilidad="privado"),
        ]
    )
    _montar(supervisor, repo)

    resp = client.get("/fuentes/pendientes")

    assert resp.status_code == 200, resp.text
    assert sorted(f["id"] for f in resp.json()) == [1, 2]


def test_seleccionar_crea_el_puntero_de_la_fuente(client, operador):
    repo = _NormaRepo([_norma(id=1, estado_visibilidad="global", propietario_id=None)])
    _montar(operador, repo)
    obra_repo = MagicMock()

    async def _guardar(obra):
        obra.id = 55
        return obra

    obra_repo.guardar = AsyncMock(side_effect=_guardar)
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo

    resp = client.post("/fuentes/1/seleccionar", json={"expediente_id": 8})

    assert resp.status_code == 201, resp.text
    assert resp.json()["obra_id"] == 55
    assert obra_repo.guardar.await_args.args[0].corpus_ref == "LIB-A"


def _obra(**kw):
    base = {
        "id": 5,
        "propietario_id": 3,
        "tipo_documento": "otro",
        "estado_visibilidad": "publicado",
        "estado_validacion": None,
        "contenido_texto": LEY,
        "nombre_archivo": "ley.pdf",
    }
    return SimpleNamespace(**{**base, **kw})


def _montar_obra(obra):
    obra_repo = MagicMock()
    obra_repo.obtener = AsyncMock(return_value=obra)
    obra_repo.marcar_promocion = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo
    return obra_repo


def test_el_operador_promueve_su_obrado_a_norma_pendiente(client, operador):
    repo = _NormaRepo()
    _montar(operador, repo)
    obra_repo = _montar_obra(_obra())

    resp = client.post(
        "/fuentes/desde-obra/5", json={"nombre": "Ley de recursos", "jerarquia": "supletoria"}
    )

    # La validacion (obra existe, es propia, publicada) es sincronica; el
    # indexado (lento) se encola, igual que POST /fuentes.
    assert resp.status_code == 202, resp.text
    assert _esperar_job(client, resp.json()["job_id"])["estado"] == "completado"
    assert repo.normas[0].estado_visibilidad == "pendiente"
    assert repo.normas[0].origen_obra_id == 5
    obra_repo.marcar_promocion.assert_awaited_once_with(5, "promovida_a_norma")


def test_promover_a_norma_un_obrado_ajeno_es_403(client, operador):
    _montar(operador, _NormaRepo())
    _montar_obra(_obra(propietario_id=99))

    resp = client.post("/fuentes/desde-obra/5", json={"nombre": "Ley", "jerarquia": "militar"})

    assert resp.status_code == 403


def test_promover_a_norma_con_jerarquia_invalida_es_422(client, operador):
    _montar(operador, _NormaRepo())
    _montar_obra(_obra())

    resp = client.post("/fuentes/desde-obra/5", json={"nombre": "Ley", "jerarquia": "doctrina"})

    assert resp.status_code == 422


def test_promover_a_norma_un_obrado_no_publicado_es_409(client, operador):
    _montar(operador, _NormaRepo())
    _montar_obra(_obra(estado_visibilidad="privado"))

    resp = client.post("/fuentes/desde-obra/5", json={"nombre": "Ley", "jerarquia": "militar"})

    assert resp.status_code == 409


def test_resoluciones_del_tribunal_lista_obrados_promovidos_y_autos_oficiales(client, operador):
    _montar(operador, _NormaRepo())
    obra_repo = MagicMock()
    obra_repo.listar_por_estado = AsyncMock(
        return_value=[
            _obra(
                id=1,
                tipo_documento="jurisprudencia",
                expediente_id=7,
                nombre_archivo="sentencia.pdf",
            ),
            _obra(id=2, tipo_documento="ejemplo", expediente_id=8, nombre_archivo="auto_vista.txt"),
            _obra(id=3, tipo_documento="sentencia", expediente_id=8, nombre_archivo="otro.pdf"),
        ]
    )
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo

    resp = client.get("/fuentes/resoluciones-tribunal")

    assert resp.status_code == 200, resp.text
    assert [(o["obra_id"], o["tipo_documento"]) for o in resp.json()] == [
        (1, "jurisprudencia"),
        (2, "ejemplo"),
    ]
    obra_repo.listar_por_estado.assert_awaited_once_with("global")
