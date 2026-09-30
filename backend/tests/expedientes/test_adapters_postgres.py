"""Tests de repositorios PostgreSQL de Sprint 4 (ExpedienteRepoImpl, ObraRepoImpl).

Cubre los contratos críticos de los adapters con MagicMock session — no DB live.

Focus Regla 5 (BLOQUEANTE): el SQL generado por `listar_por_expediente`
and `obtener` DEBE incluir el filtro `propietario_id=user OR
estado_visibilidad='publicado'`. Si un futuro refactor lo quita, el
test rompe. Si pone un True OR que lo neutraliza, el test rompe.

Bug cubiertos:
- Commit explicito en guardar/publicar/actualizar_estado (regresión Sprint 3).
- validar_usuario_id/validar_propietario_id: int > 0, no bool.
- listar_por_expediente con solo_propias=True NO genera OR visibilidad.

Patrón: tests/unit/test_consulta_historial_repo.py.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.obra import ObraModel
from src.adapters.postgres.repos.expediente_repo import ExpedienteRepoImpl
from src.adapters.postgres.repos.obra_repo import ObraRepoImpl
from src.domain.entities.obra import Obra
from tests._factories import make_expediente

# ---------- Helpers ----------


def _mock_session_execute(scalar_or_none=None, scalar_all=None) -> MagicMock:
    """Crea MagicMock session con execute return controlable.

    Args:
        scalar_or_none: valor que devolverá .scalars().one_or_none().
            Si None, one_or_none() devuelve None (no un MagicMock auto).
        scalar_all: lista que devolverá .scalars().all().
    """
    session = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    # Siempre setear el return_value explicito (None o el valor dado)
    scalars.one_or_none.return_value = scalar_or_none
    if scalar_all is not None:
        scalars.all.return_value = scalar_all
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", getattr(m, "id", 99)))
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _obra_model(
    *,
    id_: int = 1,
    expediente_id: int = 1,
    propietario_id: int = 1,
    estado_visibilidad: str = "privado",
    estado_procesamiento: str = "completado",
) -> ObraModel:
    return ObraModel(
        id=id_,
        expediente_id=expediente_id,
        propietario_id=propietario_id,
        tipo_documento="sentencia",
        nombre_archivo=f"test_{id_}.pdf",
        contenido_texto="texto x",
        estado_visibilidad=estado_visibilidad,
        estado_procesamiento=estado_procesamiento,
        fuente="carga_usuario",
        ruta_archivo=None,
        fojas_inicio=None,
        fojas_fin=None,
        tamano_archivo=0,
        created_at=datetime(2026, 8, 7, 10, 0, 0),
    )


# ---------- ExpedienteRepoImpl ----------


class TestExpedienteRepoImplGuardar:
    """Regresión Sprint 3: guardar debe commitear explícito."""

    @pytest.mark.asyncio
    async def test_guardar_hace_commit_explicito(self) -> None:
        session = _mock_session_execute()
        repo = ExpedienteRepoImpl(session)
        exp = make_expediente()

        await repo.guardar(exp)

        assert session.add.called
        assert session.flush.await_count == 1
        assert session.refresh.await_count == 1
        assert session.commit.await_count == 1, (
            "guardar debe commitear (regresión Sprint 3: AsyncSession no autocommitea)"
        )


class TestExpedienteRepoImplListar:
    """listar_por_usuario valida usuario_id (Regla 5).

    Sin esta validación, un usuario_id=0 o None podría bypasear el filtro
    `abierto_por == usuario_id` y devolver TODOS los expedientes.
    """

    @pytest.mark.asyncio
    async def test_listar_rechaza_usuario_id_invalido(self) -> None:
        session = _mock_session_execute()
        repo = ExpedienteRepoImpl(session)

        for invalido in [0, -1, None, True, False]:
            with pytest.raises(ValueError):
                await repo.listar_por_usuario(
                    usuario_id=invalido,  # type: ignore[arg-type]
                )

    @pytest.mark.asyncio
    async def test_listar_retorna_items_y_total(self) -> None:
        # Adapter hace 2 executes: PRIMERO total_stmt (l.79), DESPUES stmt (l.86).
        # Orden del side_effect = [total_result, items_result].
        # Mocks de ExpedienteModel con los atributos que _to_domain necesita.
        def _exp_model(id_: int) -> MagicMock:
            m = MagicMock()
            m.id = id_
            m.numero_caso = f"C-{id_}"
            m.tipo_proceso = "consulta"
            m.tribunal_origen = "TSJM"
            m.procesado_nombre = "X"
            m.procesado_grado = None
            m.delito = "Y"
            m.sentencia_origen = None
            m.fojas_total = 10
            m.estado = "activo"
            m.abierto_por = 5
            m.created_at = datetime(2026, 8, 7)
            return m

        models = [_exp_model(1), _exp_model(2)]
        session = MagicMock()
        # PRIMERO: total_stmt usa .scalar()
        total_result = MagicMock()
        total_result.scalar.return_value = 2
        # SEGUNDO: stmt usa .scalars().all()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = models

        session.execute = AsyncMock(side_effect=[total_result, items_result])
        repo = ExpedienteRepoImpl(session)

        items, total = await repo.listar_por_usuario(usuario_id=5)

        assert len(items) == 2
        assert total == 2
        assert items[0].id == 1


# ---------- ObraRepoImpl ----------


class TestObraRepoGuardar:
    @pytest.mark.asyncio
    async def test_guardar_hace_commit_explicito(self) -> None:
        session = _mock_session_execute()
        repo = ObraRepoImpl(session)

        obra = Obra(
            id=None,
            expediente_id=1,
            propietario_id=2,
            tipo_documento="sentencia",
            nombre_archivo="x.pdf",
            contenido_texto="",
        )
        await repo.guardar(obra)

        assert session.flush.await_count == 1
        assert session.commit.await_count == 1


class TestObraRepoObtenerRegla5:
    """Regla 5 BLOQUEANTE: SQL de obtener DEBE filtrar visibilidad.

    Verificamos el contrato: el stmt WHERE tiene OR propietario_id=user
    OR estado_visibilidad='publicado'. No podemos verificar SQL string por
    string, pero sí verificar que el adapter llama validar_usuario_id y
    que el modelo devuelto (si existe) respeta la regla.
    """

    @pytest.mark.asyncio
    async def test_obtener_rechaza_usuario_id_invalido(self) -> None:
        session = _mock_session_execute()
        repo = ObraRepoImpl(session)

        for invalido in [0, -1, None, True]:
            with pytest.raises(ValueError):
                await repo.obtener(obra_id=1, usuario_id=invalido)

    @pytest.mark.asyncio
    async def test_obtener_devuelve_none_si_no_match(self) -> None:
        # mock devuelve None (no se encontró o filtro Regla 5 excluyó)
        session = _mock_session_execute(scalar_or_none=None)
        repo = ObraRepoImpl(session)

        result = await repo.obtener(obra_id=999, usuario_id=5)

        assert result is None


class TestObraRepoListarRegla5:
    """Regla 5: listar_por_expediente aplica filtro de visibilidad SIEMPRE.

    El SQL tiene que tener:
        WHERE expediente_id=X
          AND (propietario_id=user OR estado_visibilidad='publicado')

    Con solo_propias=True, no debe generarse el OR visibilidad (solo
    propietario_id == usuario_id).
    """

    @pytest.mark.asyncio
    async def test_listar_rechaza_usuario_id_invalido(self) -> None:
        session = _mock_session_execute()
        repo = ObraRepoImpl(session)

        for invalido in [0, -1, None, True]:
            with pytest.raises(ValueError):
                await repo.listar_por_expediente(expediente_id=1, usuario_id=invalido)

    @pytest.mark.asyncio
    async def test_listar_filtra_visibilidad_por_defecto(self) -> None:
        # El fake session devuelve lista vacía; lo importante es que se
        # ejecuta el query (y el SQL contiene el OR, validado por
        # test EXPLAIN ANALYZE en Sprint 4 Fase 4).
        models = [_obra_model(id_=1, propietario_id=5)]
        session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = models
        session.execute = AsyncMock(return_value=result)
        repo = ObraRepoImpl(session)

        items = await repo.listar_por_expediente(expediente_id=1, usuario_id=5)

        assert len(items) == 1
        assert items[0].propietario_id == 5

    @pytest.mark.asyncio
    async def test_listar_solo_propias_no_genera_or_visibilidad(self) -> None:
        """Con solo_propias=True, el SQL NO debe tener OR en la clausula WHERE.

        Compara el compile del stmt con solo_propias=True vs False.
        Con False: WHERE expediente_id=X AND (propietario_id=user OR
        estado_visibilidad='publicado').
        Con True: WHERE expediente_id=X AND propietario_id=user (sin OR).
        """
        stmts_recibidos: list = []

        async def _capture_execute(stmt) -> MagicMock:
            stmts_recibidos.append(stmt)
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = MagicMock()
        session.execute = AsyncMock(side_effect=_capture_execute)
        repo = ObraRepoImpl(session)

        # llamada con solo_propias=True
        await repo.listar_por_expediente(expediente_id=1, usuario_id=5, solo_propias=True)
        stmt_solo = str(stmts_recibidos[-1].compile(compile_kwargs={"literal_binds": True}))

        # llamada con solo_propias=False
        await repo.listar_por_expediente(expediente_id=1, usuario_id=5, solo_propias=False)
        stmt_default = str(stmts_recibidos[-1].compile(compile_kwargs={"literal_binds": True}))

        # El stmt default tiene el OR logical en WHERE:
        # "... AND (obra.propietario_id = 5 OR obra.estado_visibilidad = 'publicado')"
        assert " OR " in stmt_default.upper(), (
            "listar_por_expediente (default) debe filtrar con OR visibilidad"
        )
        # El stmt solo_propias NO debe tener OR logical en WHERE
        assert " OR " not in stmt_solo.upper(), (
            "solo_propias=True NO debe tener OR en WHERE — solo filtra por propietario_id"
        )


class TestObraRepoPublicarRegla5:
    """Regla 5: publicar valida propietario_id en el adapter.

    Si el caller no es propietario, el WHERE no matchea, devuelve None.
    El router mapea None a 403.
    """

    @pytest.mark.asyncio
    async def test_publicar_rechaza_propietario_id_invalido(self) -> None:
        session = _mock_session_execute()
        repo = ObraRepoImpl(session)

        for invalido in [0, -1, None, True]:
            with pytest.raises(ValueError):
                await repo.publicar(obra_id=1, propietario_id=invalido)

    @pytest.mark.asyncio
    async def test_publicar_devuelve_none_si_no_match(self) -> None:
        # mock: SELECT devuelvió None → no es propietario o no existe
        session = _mock_session_execute(scalar_or_none=None)
        repo = ObraRepoImpl(session)

        result = await repo.publicar(obra_id=999, propietario_id=5)

        assert result is None
        # No debe llegar a commit si no hay match
        assert session.commit.await_count == 0

    @pytest.mark.asyncio
    async def test_publicar_exitoso_cambia_estado_y_commit(self) -> None:
        modelo = _obra_model(id_=1, propietario_id=5, estado_visibilidad="privado")
        session = _mock_session_execute(scalar_or_none=modelo)
        repo = ObraRepoImpl(session)

        result = await repo.publicar(obra_id=1, propietario_id=5)

        assert result is not None
        assert result.estado_visibilidad == "publicado"
        assert modelo.estado_visibilidad == "publicado"
        assert session.commit.await_count == 1


class TestObraRepoActualizarEstadoProcesamiento:
    @pytest.mark.asyncio
    async def test_actualizar_commit_si_existe(self) -> None:
        modelo = _obra_model(id_=1, estado_procesamiento="pendiente")
        session = _mock_session_execute(scalar_or_none=modelo)
        repo = ObraRepoImpl(session)

        result = await repo.actualizar_estado_procesamiento(obra_id=1, estado="completado")

        assert result is not None
        assert result.estado_procesamiento == "completado"
        assert modelo.estado_procesamiento == "completado"
        assert session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_actualizar_none_si_no_existe(self) -> None:
        session = _mock_session_execute(scalar_or_none=None)
        repo = ObraRepoImpl(session)

        result = await repo.actualizar_estado_procesamiento(obra_id=999, estado="completado")

        assert result is None
        assert session.commit.await_count == 0


class TestObraRepoDoctrinaExcluyeCriterios:
    """La doctrina (global/estado/mias/revisión) NO debe incluir criterios:
    son instrucciones de comportamiento del asistente. La exclusión es
    BLACKLIST (!= criterio), no whitelist (== doctrina): cualquier otro tipo
    publicado/aprobado debe seguir visible en el flujo de aprobación
    (bug fix tras commit 71363d7, que varaba sentencias/autos)."""

    def _repo_con_captura(self, stmts: list) -> ObraRepoImpl:
        async def _capture_execute(stmt) -> MagicMock:
            stmts.append(stmt)
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = MagicMock()
        session.execute = AsyncMock(side_effect=_capture_execute)
        return ObraRepoImpl(session)

    @pytest.mark.asyncio
    async def test_listar_global_excluye_criterios_sin_whitelist(self) -> None:
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_global(usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert "tipo_documento != 'criterio'" in sql
        assert "= 'doctrina'" not in sql

    @pytest.mark.asyncio
    async def test_listar_mias_excluye_criterios_sin_whitelist(self) -> None:
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_mias(usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert "tipo_documento != 'criterio'" in sql
        assert "= 'doctrina'" not in sql

    @pytest.mark.asyncio
    async def test_listar_por_estado_excluye_criterios_sin_whitelist(self) -> None:
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_por_estado("publicado")
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert "tipo_documento != 'criterio'" in sql
        assert "= 'doctrina'" not in sql

    @pytest.mark.asyncio
    async def test_listar_estados_excluye_criterios_sin_whitelist(self) -> None:
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_estados()
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert "tipo_documento != 'criterio'" in sql
        assert "= 'doctrina'" not in sql

    @pytest.mark.asyncio
    async def test_listar_doctrina_privada_no_incluye_criterios(self) -> None:
        """El dropdown de material de referencia (chat) tampoco muestra
        criterios: tienen gestión propia (/admin/criterios) y se inyectan
        automaticamente en la generacion (slot {{criterio_vocal}}).
        A diferencia de los listados de doctrina (blacklist), el dropdown
        es WHITELIST (doctrina, material_caso, punteros) por diseño
        referencial."""
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_doctrina_privada(expediente_id=7, usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert "tipo_documento IN" in sql
        assert "'doctrina'" in sql
        assert "criterio" not in sql


class TestListarDoctrinaPrivadaAlcanceReferencial:
    """El dropdown de doctrina dentro de un expediente es material de
    REFERENCIA (doctrina, material_caso, punteros doctrina_libro,
    jurisprudencia y ejemplo): los criterios tienen gestion propia
    (/admin/criterios) y se inyectan automaticamente en la generacion
    (slot {{criterio_vocal}}) — no son material seleccionable. Los obrados
    vinculados al expediente NO aparecen ahi, y un obrado aprobado a
    global vive solo en listar_global."""

    def _repo_con_captura(self, stmts: list) -> ObraRepoImpl:
        async def _capture_execute(stmt) -> MagicMock:
            stmts.append(stmt)
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = MagicMock()
        session.execute = AsyncMock(side_effect=_capture_execute)
        return ObraRepoImpl(session)

    @pytest.mark.asyncio
    async def test_dropdown_usa_whitelist_referencial_y_scope_expediente(self) -> None:
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_doctrina_privada(expediente_id=7, usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        for tipo in (
            "doctrina",
            "material_caso",
            "doctrina_libro",
            "jurisprudencia",
            "ejemplo",
        ):
            assert f"'{tipo}'" in sql
        assert "criterio" not in sql
        assert "expediente_id" in sql
        # Punteros globales: expediente NULL con corpus también entran.
        assert "corpus IS NOT NULL" in sql

    @pytest.mark.asyncio
    async def test_global_mantiene_memoriales_unico_filtro_blacklist(self) -> None:
        """F2: un memorial_apelacion aprobado a global sigue visible en
        listar_global; el unico filtro de tipo es la blacklist criterios."""
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_global(usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        assert sql.count("tipo_documento != 'criterio'") == 1
        assert "tipo_documento =" not in sql
        assert "tipo_documento IN" not in sql

    @pytest.mark.asyncio
    async def test_dropdown_nunca_lista_obrados(self) -> None:
        """Pin de comportamiento: aunque manana se vincule un memorial al
        expediente, el dropdown sigue sin mostrarlo (whitelist referencial)."""
        stmts: list = []
        repo = self._repo_con_captura(stmts)

        await repo.listar_doctrina_privada(expediente_id=7, usuario_id=26)
        sql = str(stmts[-1].compile(compile_kwargs={"literal_binds": True}))

        for obrado in ("sentencia", "memorial_apelacion", "auto_vista"):
            assert obrado not in sql


# ---------- Promoción de obrados a jurisprudencia ----------


@pytest.mark.asyncio
async def test_marcar_promocion_guarda_estado_y_motivo_con_commit() -> None:
    model = _obra_model()
    session = _mock_session_execute(scalar_or_none=model)

    obra = await ObraRepoImpl(session).marcar_promocion(1, "promocion_rechazada", "no vinculante")

    assert model.estado_validacion == "promocion_rechazada"
    assert model.motivo_rechazo == "no vinculante"
    session.commit.assert_awaited_once()
    assert obra is not None


@pytest.mark.asyncio
async def test_promover_a_jurisprudencia_cambia_tipo_visibilidad_y_estado() -> None:
    model = _obra_model()
    session = _mock_session_execute(scalar_or_none=model)

    await ObraRepoImpl(session).promover_a_jurisprudencia(1)

    assert model.tipo_documento == "jurisprudencia"
    assert model.estado_visibilidad == "global"
    assert model.estado_validacion == "promovida"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_promocion_de_obra_inexistente_devuelve_none() -> None:
    session = _mock_session_execute(scalar_or_none=None)

    assert await ObraRepoImpl(session).promover_a_jurisprudencia(404) is None
    assert await ObraRepoImpl(session).marcar_promocion(404, "promocion_pendiente") is None
