"""Tests del ciclo "obrado -> oficial -> ejemplo global" (niveles-corpus N4).

Extraidos de test_borradores_router.py: el archivo mezclaba los tests de
generacion/CRUD con el ciclo editorial completo (solicitar/aprobar/
desoficializar oficial + ejemplo global visible en /doctrina/ejemplos).

TDD con TestClient + dependency_overrides: no toca DB, Ollama, ni Qdrant.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import install_permiso_repo_override
from fastapi.testclient import TestClient

from src.adapters.http import dependencies as deps
from src.adapters.http import dependencies_borradores as bdeps
from src.domain.entities.borrador import Borrador
from src.domain.entities.usuario import Usuario
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


# --- Plan (ciclo obrado -> oficial) ---


def _make_borrador_ciclo(estado: str) -> Borrador:
    return Borrador(
        id=42,
        expediente_id=7,
        propietario_id=OPERADOR.id,
        tipo="auto_vista_consulta",
        contenido="borrador x",
        estado=estado,  # type: ignore[arg-type]
        activo=True,
    )


def _override_borrador_repo_ciclo(
    *, resultado: Borrador | None = None, supervisor_result: Borrador | None = None
):
    repo = MagicMock()
    repo.actualizar_estado = AsyncMock(return_value=resultado)
    repo.actualizar_estado_supervisor = AsyncMock(return_value=supervisor_result)
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    return repo


def _override_auth_repo():
    from src.adapters.http.dependencies import get_auth_repo

    auth = MagicMock()
    auth.get_by_id = AsyncMock(return_value=OPERADOR)
    fastapi_app.dependency_overrides[get_auth_repo] = lambda: auth


def test_solicitar_oficial_200_operador(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    borrador = _make_borrador_ciclo(estado="pendiente_oficial")
    repo = _override_borrador_repo_ciclo(resultado=borrador)
    _override_auth_repo()

    resp = client.post("/borradores/42/solicitar-oficial")

    assert resp.status_code == 200
    repo.actualizar_estado.assert_awaited_once_with(42, "pendiente_oficial", propietario_id=2)


def test_solicitar_oficial_404_si_no_propietario(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    _override_borrador_repo_ciclo(resultado=None)

    resp = client.post("/borradores/42/solicitar-oficial")

    assert resp.status_code == 404


def test_aprobar_oficial_supervisor(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    # El stack completo evita que get_vector_repo/get_embedder abran conexiones reales.
    repo, _obra_repo, _guardadas = _override_aprobar_stack(borrador)

    resp = client.post("/borradores/42/aprobar-oficial")

    assert resp.status_code == 200
    repo.actualizar_estado_supervisor.assert_awaited_once_with(
        42, "oficial", desde="pendiente_oficial"
    )


def test_aprobar_oficial_operador_403(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    _override_borrador_repo_ciclo()

    resp = client.post("/borradores/42/aprobar-oficial")

    assert resp.status_code == 403


def _override_obra_repo_ejemplos() -> MagicMock:
    from src.adapters.http import dependencies as deps

    obra_repo = MagicMock()
    obra_repo.archivar_ejemplos_borrador = AsyncMock(return_value=1)
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo
    return obra_repo


def test_desoficializar_supervisor(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="publicado")
    repo = _override_borrador_repo_ciclo(supervisor_result=borrador)
    _override_auth_repo()
    obra_repo = _override_obra_repo_ejemplos()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "publicado"})

    assert resp.status_code == 200
    repo.actualizar_estado_supervisor.assert_awaited_once_with(42, "publicado", desde="oficial")
    obra_repo.archivar_ejemplos_borrador.assert_awaited_once_with(7, 42)


def _audit_fake() -> MagicMock:
    fake = MagicMock()
    fake.registrar = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_audit_log_repo_dep] = lambda: fake
    return fake


def test_solicitar_oficial_se_audita(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    _override_borrador_repo_ciclo(resultado=_make_borrador_ciclo(estado="pendiente_oficial"))
    _override_auth_repo()
    audit = _audit_fake()

    assert client.post("/borradores/42/solicitar-oficial").status_code == 200

    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.usuario_id, r.entidad, r.entidad_id) == (
        "solicitar_oficial",
        OPERADOR.id,
        "borrador",
        42,
    )


def test_aprobar_oficial_se_audita(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    _override_aprobar_stack(_make_borrador_ciclo(estado="oficial"))
    audit = _audit_fake()

    assert client.post("/borradores/42/aprobar-oficial").status_code == 200

    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.usuario_id, r.entidad_id) == ("aprobar_oficial", SUPERVISOR.id, 42)


def test_desoficializar_se_audita_con_el_destino(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    _override_borrador_repo_ciclo(
        supervisor_result=_make_borrador_ciclo(estado="pendiente_oficial")
    )
    _override_auth_repo()
    _override_obra_repo_ejemplos()
    audit = _audit_fake()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "pendiente_oficial"})

    assert resp.status_code == 200
    r = audit.registrar.await_args.args[0]
    assert (r.accion, r.entidad_id, r.detalle) == (
        "desoficializar",
        42,
        {"destino": "pendiente_oficial"},
    )


def test_desoficializar_puede_volver_a_solicitud_de_oficializacion(client: TestClient) -> None:
    """Para corregir un oficial: desoficializar -> pendiente_oficial (F-07)."""
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="pendiente_oficial")
    repo = _override_borrador_repo_ciclo(supervisor_result=borrador)
    _override_auth_repo()
    obra_repo = _override_obra_repo_ejemplos()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "pendiente_oficial"})

    assert resp.status_code == 200
    repo.actualizar_estado_supervisor.assert_awaited_once_with(
        42, "pendiente_oficial", desde="oficial"
    )
    obra_repo.archivar_ejemplos_borrador.assert_awaited_once_with(7, 42)  # el ejemplo se archiva


def test_desoficializar_rechaza_destinos_invalidos(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    _override_borrador_repo_ciclo()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "oficial"})

    assert resp.status_code == 422


def test_desoficializar_un_borrador_que_no_es_oficial_da_404(client: TestClient) -> None:
    """El repo devuelve None si el estado actual no es 'oficial' (F-35)."""
    _override_current_user(SUPERVISOR)
    _override_borrador_repo_ciclo(supervisor_result=None)
    _override_obra_repo_ejemplos()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "publicado"})

    assert resp.status_code == 404


def test_desoficializar_operador_403(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    _override_borrador_repo_ciclo()

    resp = client.post("/borradores/42/desoficializar", json={"destino": "borrador"})

    assert resp.status_code == 403


# --- N4 (niveles-corpus): oficializar crea ejemplo + bloqueo operador ---


def _override_aprobar_stack(borrador: Borrador, *, existe_ejemplo: bool = False):
    from src.adapters.http import dependencies as deps

    repo = _override_borrador_repo_ciclo(supervisor_result=borrador)
    _override_auth_repo()

    expediente_repo = MagicMock()
    expediente_repo.obtener = AsyncMock(
        return_value=__import__("types").SimpleNamespace(
            id=7, tribunal_origen="TPJM", estado="activo"
        )
    )
    fastapi_app.dependency_overrides[deps.get_expediente_repo_dep] = lambda: expediente_repo

    guardadas: list = []

    async def _guardar(obra):
        obra.id = 100 + len(guardadas)
        guardadas.append(obra)
        return obra

    obra_repo = MagicMock()
    obra_repo.guardar = AsyncMock(side_effect=_guardar)
    obra_repo.existe_obra = AsyncMock(return_value=existe_ejemplo)
    fastapi_app.dependency_overrides[deps.get_obra_repo_dep] = lambda: obra_repo

    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda frags: frags)
    fastapi_app.dependency_overrides[deps.get_fragmento_repo] = lambda: fragmento_repo

    vector_repo = MagicMock()
    vector_repo.upsert_corpus = AsyncMock()
    fastapi_app.dependency_overrides[deps.get_vector_repo] = lambda: vector_repo

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 8])
    fastapi_app.dependency_overrides[deps.get_embedder] = lambda: embedder

    return repo, obra_repo, guardadas


def test_aprobar_oficial_crea_ejemplo_global(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    _repo, obra_repo, guardadas = _override_aprobar_stack(borrador)

    resp = client.post("/borradores/42/aprobar-oficial")

    assert resp.status_code == 200
    tipos = [o.tipo_documento for o in guardadas]
    assert "ejemplo" in tipos
    ejemplo = next(o for o in guardadas if o.tipo_documento == "ejemplo")
    assert ejemplo.estado_visibilidad == "global"
    assert ejemplo.expediente_id == 7


def test_aprobar_oficial_loguea_si_falla_la_indexacion(client: TestClient, caplog) -> None:
    """Oficializar no se bloquea por un fallo de indexado, pero debe dejar rastro (F-20)."""
    from src.adapters.http import dependencies as deps

    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    _override_aprobar_stack(borrador)
    embedder = MagicMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("embedder caido"))
    fastapi_app.dependency_overrides[deps.get_embedder] = lambda: embedder

    with caplog.at_level("ERROR"):
        resp = client.post("/borradores/42/aprobar-oficial")

    assert resp.status_code == 200
    assert "obra_id=100" in caplog.text


def test_aprobar_oficial_no_duplica_ejemplo(client: TestClient) -> None:
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    _repo, obra_repo, guardadas = _override_aprobar_stack(borrador, existe_ejemplo=True)

    resp = client.post("/borradores/42/aprobar-oficial")

    assert resp.status_code == 200
    assert [o.tipo_documento for o in guardadas].count("ejemplo") == 0


def test_patch_operador_403_si_oficial(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_propietario = AsyncMock()
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    _override_auth_repo()

    resp = client.patch("/borradores/42", json={"contenido": "nuevo"})

    assert resp.status_code == 403
    repo.actualizar_contenido_propietario.assert_not_called()


def test_patch_operador_200_si_no_oficial(client: TestClient) -> None:
    _override_current_user(OPERADOR)
    borrador = _make_borrador_ciclo(estado="publicado")
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_propietario = AsyncMock(return_value=borrador)
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    _override_auth_repo()

    resp = client.patch("/borradores/42", json={"contenido": "nuevo"})

    assert resp.status_code == 200
    repo.actualizar_contenido_propietario.assert_awaited_once()


def test_patch_supervisor_edita_el_contenido_de_un_pendiente_oficial_ajeno(
    client: TestClient,
) -> None:
    """El supervisor corrige durante la revision (pendiente_oficial), antes de aprobar (F-07)."""
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="pendiente_oficial")  # propietario: OPERADOR
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_supervisor = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_propietario = AsyncMock(return_value=None)
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    _override_auth_repo()

    resp = client.patch("/borradores/42", json={"contenido": "corregido"})

    assert resp.status_code == 200
    repo.actualizar_contenido_supervisor.assert_awaited_once_with(
        42, contenido="corregido", layout=None
    )
    repo.actualizar_contenido_propietario.assert_not_called()
    # El autor devuelto es el dueño (operador), no el supervisor que corrigió.
    from src.adapters.http.dependencies import get_auth_repo

    auth = fastapi_app.dependency_overrides[get_auth_repo]()
    auth.get_by_id.assert_awaited_with(borrador.propietario_id)
    assert borrador.propietario_id != SUPERVISOR.id


def test_patch_operador_no_edita_su_borrador_en_pendiente_oficial(client: TestClient) -> None:
    """Solicitado el oficial, el propietario ya no edita: solo el supervisor (F-07)."""
    _override_current_user(OPERADOR)
    borrador = _make_borrador_ciclo(estado="pendiente_oficial")
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_supervisor = AsyncMock()
    repo.actualizar_contenido_propietario = AsyncMock(return_value=None)  # estado != borrador
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    _override_auth_repo()

    resp = client.patch("/borradores/42", json={"contenido": "x"})

    assert resp.status_code == 404
    repo.actualizar_contenido_supervisor.assert_not_called()


def test_n4_ciclo_publicado_a_ejemplo_global(client: TestClient) -> None:
    """Ciclo N4: publicado -> oficial crea ejemplo global visible en
    GET /fuentes/resoluciones-tribunal (sin colar material_caso); operador bloqueado
    en PATCH y el supervisor debe desoficializar antes de corregir."""
    from src.domain.entities.obra import Obra

    # 1. Supervisor oficializa: nace obra tipo=ejemplo global.
    _override_current_user(SUPERVISOR)
    borrador = _make_borrador_ciclo(estado="oficial")
    _repo, obra_repo, guardadas = _override_aprobar_stack(borrador)
    resp = client.post("/borradores/42/aprobar-oficial")
    assert resp.status_code == 200
    ejemplo = next(o for o in guardadas if o.tipo_documento == "ejemplo")
    assert ejemplo.estado_visibilidad == "global"
    ejemplo.id = 201

    # 2. GET /fuentes/resoluciones-tribunal lo lista (jurisprudencia del tribunal);
    # material_caso no se cuela.
    decoy = Obra(
        id=202,
        expediente_id=7,
        propietario_id=2,
        tipo_documento="material_caso",
        nombre_archivo="apunte.pdf",
        contenido_texto="x",
        ruta_archivo=None,
        estado_visibilidad="global",
        fuente="carga_usuario",
        tamano_archivo=1,
        estado_procesamiento="completado",
        autor_instancia=None,
        autor=None,
        fecha_documento=None,
        procedencia=None,
        estado_validacion=None,
        motivo_rechazo=None,
        recomendada=False,
        activo=True,
    )
    obra_repo.listar_por_estado = AsyncMock(return_value=[ejemplo, decoy])
    _override_current_user(OPERADOR)
    resp = client.get("/fuentes/resoluciones-tribunal")
    assert resp.status_code == 200
    nombres = [i["nombre_archivo"] for i in resp.json()]
    assert ejemplo.nombre_archivo in nombres
    assert "apunte.pdf" not in nombres

    # 3. Operador bloqueado en PATCH; el supervisor tampoco edita un oficial.
    _override_current_user(OPERADOR)
    repo = MagicMock()
    repo.obtener_por_id = AsyncMock(return_value=borrador)
    repo.actualizar_contenido_propietario = AsyncMock()
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    _override_auth_repo()
    resp = client.patch("/borradores/42", json={"contenido": "x"})
    assert resp.status_code == 403
    repo.actualizar_contenido_propietario.assert_not_called()

    # El supervisor tampoco edita un oficial: primero lo desoficializa (F-07).
    _override_current_user(SUPERVISOR)
    repo.actualizar_contenido_supervisor = AsyncMock(return_value=borrador)
    fastapi_app.dependency_overrides[bdeps.get_borrador_repo_dep] = lambda: repo
    resp = client.patch("/borradores/42", json={"contenido": "y"})
    assert resp.status_code == 403
    repo.actualizar_contenido_supervisor.assert_not_called()
    repo.actualizar_contenido_propietario.assert_not_called()
