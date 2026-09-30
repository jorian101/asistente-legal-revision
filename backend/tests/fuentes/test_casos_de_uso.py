"""Casos de uso comunes de fuentes: norma, jurisprudencia y doctrina (libros).

Flujo privada -> pendiente -> global. El operador propone y el supervisor
aprueba; el supervisor puede cargar directo a global.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.fuentes.abreviatura import generar_abreviatura
from src.application.fuentes.casos_de_uso import (
    FuenteNoEncontradaError,
    FuenteNoPropiaError,
    ListarFuentes,
    ProponerFuente,
    ResolverFuente,
    SubirFuente,
    TransicionInvalidaError,
)


def _norma(**kw):
    base = {
        "id": 1,
        "abreviatura": "LIB-A",
        "nombre": "Libro A",
        "tipo": "doctrina_libro",
        "jerarquia": "doctrina",
        "indexado": True,
        "activo": True,
        "propietario_id": 10,
        "estado_visibilidad": "privado",
        "motivo_rechazo": None,
    }
    return SimpleNamespace(**{**base, **kw})


def _repos(normas):
    norma_repo = MagicMock()
    norma_repo.list_all = AsyncMock(return_value=normas)
    norma_repo.get_by_id = AsyncMock(
        side_effect=lambda i: next((n for n in normas if n.id == i), None)
    )
    norma_repo.get_by_abreviatura = AsyncMock(
        side_effect=lambda a: next((n for n in normas if n.abreviatura == a), None)
    )
    norma_repo.actualizar_visibilidad = AsyncMock(
        side_effect=lambda i, estado, motivo=None: SimpleNamespace(
            **{
                **next(vars(n) for n in normas if n.id == i),
                "estado_visibilidad": estado,
                "motivo_rechazo": motivo,
            }
        )
    )
    vector = MagicMock()
    vector.actualizar_payload_norma = AsyncMock()
    return norma_repo, {"norma": vector, "jurisprudencia": vector, "doctrina": vector}, vector


# ---------- abreviatura ----------


@pytest.mark.asyncio
async def test_la_abreviatura_lleva_el_prefijo_de_la_categoria_y_es_unica():
    repo = MagicMock()
    repo.get_by_abreviatura = AsyncMock(side_effect=[object(), None])  # la 1a esta ocupada

    abrev = await generar_abreviatura("doctrina", "Manual de Argumentación (2ª ed.)", repo)

    assert abrev == "LIB-MANUAL-DE-ARGUMENTACION-2A-ED-2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "categoria,prefijo", [("norma", "LEY-"), ("jurisprudencia", "JUR-"), ("doctrina", "LIB-")]
)
async def test_prefijo_por_categoria(categoria, prefijo):
    repo = MagicMock()
    repo.get_by_abreviatura = AsyncMock(return_value=None)

    assert (await generar_abreviatura(categoria, "Algo", repo)).startswith(prefijo)


# ---------- listar ----------


@pytest.mark.asyncio
async def test_listar_muestra_lo_global_lo_propio_y_las_pendientes_solo_al_supervisor():
    normas = [
        _norma(id=1, estado_visibilidad="global", propietario_id=None),
        _norma(id=2, estado_visibilidad="privado", propietario_id=10),
        _norma(id=3, estado_visibilidad="privado", propietario_id=99),
        _norma(id=4, estado_visibilidad="pendiente", propietario_id=99),
        _norma(id=5, jerarquia="suprema", tipo="constitucion", estado_visibilidad="global"),
    ]
    repo, _, _ = _repos(normas)

    operador = await ListarFuentes(repo).ejecutar("doctrina", usuario_id=10, es_supervisor=False)
    supervisor = await ListarFuentes(repo).ejecutar("doctrina", usuario_id=1, es_supervisor=True)

    assert [f.id for f in operador] == [1, 2]
    assert [f.id for f in supervisor] == [1, 4]
    assert operador[1].es_propia is True


@pytest.mark.asyncio
async def test_jurisprudencia_se_divide_en_tcp_y_cidh():
    normas = [
        _norma(id=1, jerarquia="jurisprudencia", tipo="scp_tcp", estado_visibilidad="global"),
        _norma(
            id=2, jerarquia="jurisprudencia", tipo="sentencia_cidh", estado_visibilidad="global"
        ),
    ]
    repo, _, _ = _repos(normas)

    fuentes = await ListarFuentes(repo).ejecutar(
        "jurisprudencia", usuario_id=10, es_supervisor=False
    )

    assert [f.subgrupo for f in fuentes] == ["tcp", "cidh"]


@pytest.mark.asyncio
async def test_no_lista_inactivas_ni_sin_indexar():
    repo, _, _ = _repos(
        [
            _norma(id=1, estado_visibilidad="global", activo=False),
            _norma(id=2, estado_visibilidad="global", indexado=False),
        ]
    )

    assert await ListarFuentes(repo).ejecutar("doctrina", usuario_id=10, es_supervisor=True) == []


# ---------- subir ----------


@pytest.mark.asyncio
async def test_el_operador_sube_privado_y_el_supervisor_directo_a_global():
    indexar = MagicMock()
    indexar.ejecutar = AsyncMock(
        return_value=SimpleNamespace(norma_id=7, qdrant_collection="doctrina")
    )
    repo = MagicMock()
    repo.get_by_abreviatura = AsyncMock(return_value=None)
    uc = SubirFuente(indexar, repo)

    await uc.ejecutar(
        categoria="doctrina",
        nombre="Mi libro",
        ruta="/tmp/x.txt",
        texto="t",
        usuario_id=10,
        es_supervisor=False,
    )
    req_op = indexar.ejecutar.await_args.args[0]
    await uc.ejecutar(
        categoria="doctrina",
        nombre="Otro",
        ruta="/tmp/y.txt",
        texto="t",
        usuario_id=20,
        es_supervisor=True,
    )
    req_sup = indexar.ejecutar.await_args.args[0]

    assert (req_op.estado_visibilidad, req_op.propietario_id) == ("privado", 10)
    assert (req_sup.estado_visibilidad, req_sup.propietario_id) == ("global", 20)
    assert req_op.abreviatura.startswith("LIB-MI-LIBRO")


# ---------- proponer ----------


@pytest.mark.asyncio
async def test_el_dueno_propone_y_se_actualiza_qdrant():
    repo, vectores, vector = _repos([_norma(id=1, estado_visibilidad="privado", propietario_id=10)])

    fuente = await ProponerFuente(repo, vectores).ejecutar(fuente_id=1, usuario_id=10)

    repo.actualizar_visibilidad.assert_awaited_once_with(1, "pendiente", None)
    vector.actualizar_payload_norma.assert_awaited_once_with(1, {"visibilidad": "pendiente"})
    assert fuente.estado_visibilidad == "pendiente"


@pytest.mark.asyncio
async def test_solo_el_dueno_propone():
    repo, vectores, _ = _repos([_norma(id=1, propietario_id=99)])

    with pytest.raises(FuenteNoPropiaError):
        await ProponerFuente(repo, vectores).ejecutar(fuente_id=1, usuario_id=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["pendiente", "global", "rechazado"])
async def test_solo_se_propone_lo_privado(estado):
    repo, vectores, _ = _repos([_norma(id=1, estado_visibilidad=estado, propietario_id=10)])

    with pytest.raises(TransicionInvalidaError):
        await ProponerFuente(repo, vectores).ejecutar(fuente_id=1, usuario_id=10)


@pytest.mark.asyncio
async def test_proponer_fuente_inexistente():
    repo, vectores, _ = _repos([])

    with pytest.raises(FuenteNoEncontradaError):
        await ProponerFuente(repo, vectores).ejecutar(fuente_id=9, usuario_id=10)


# ---------- resolver ----------


@pytest.mark.asyncio
async def test_el_supervisor_aprueba_y_pasa_a_global():
    repo, vectores, vector = _repos([_norma(id=1, estado_visibilidad="pendiente")])

    fuente = await ResolverFuente(repo, vectores).ejecutar(fuente_id=1, aprobar=True)

    repo.actualizar_visibilidad.assert_awaited_once_with(1, "global", None)
    vector.actualizar_payload_norma.assert_awaited_once_with(1, {"visibilidad": "global"})
    assert fuente.estado_visibilidad == "global"


@pytest.mark.asyncio
async def test_rechazar_exige_motivo_y_no_toca_qdrant():
    repo, vectores, vector = _repos([_norma(id=1, estado_visibilidad="pendiente")])

    with pytest.raises(ValueError):
        await ResolverFuente(repo, vectores).ejecutar(fuente_id=1, aprobar=False)

    await ResolverFuente(repo, vectores).ejecutar(
        fuente_id=1, aprobar=False, motivo="no es un libro"
    )
    repo.actualizar_visibilidad.assert_awaited_once_with(1, "rechazado", "no es un libro")
    vector.actualizar_payload_norma.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_se_resuelve_lo_global():
    repo, vectores, _ = _repos([_norma(id=1, estado_visibilidad="global")])

    with pytest.raises(TransicionInvalidaError):
        await ResolverFuente(repo, vectores).ejecutar(fuente_id=1, aprobar=True)


@pytest.mark.asyncio
async def test_si_qdrant_falla_el_cambio_de_estado_no_se_revierte():
    repo, vectores, vector = _repos([_norma(id=1, estado_visibilidad="pendiente")])
    vector.actualizar_payload_norma = AsyncMock(side_effect=RuntimeError("caido"))

    await ResolverFuente(repo, vectores).ejecutar(fuente_id=1, aprobar=True)

    repo.actualizar_visibilidad.assert_awaited_once()


# ---------- promover un obrado a norma ----------


def _obra(**kw):
    base = {
        "id": 5,
        "propietario_id": 10,
        "tipo_documento": "otro",
        "estado_visibilidad": "publicado",
        "estado_validacion": None,
        "contenido_texto": "Artículo 1. (Objeto). Regula.",
        "nombre_archivo": "ley.pdf",
        "activo": True,
    }
    return SimpleNamespace(**{**base, **kw})


def _promotor(obra):
    from src.application.fuentes.casos_de_uso import PromoverObraANorma

    indexar = MagicMock()
    indexar.ejecutar = AsyncMock(
        return_value=SimpleNamespace(norma_id=7, qdrant_collection="corpus_juridico")
    )
    norma_repo = MagicMock()
    norma_repo.get_by_abreviatura = AsyncMock(return_value=None)
    obra_repo = MagicMock()
    obra_repo.obtener = AsyncMock(return_value=obra)
    obra_repo.marcar_promocion = AsyncMock()
    return PromoverObraANorma(indexar, norma_repo, obra_repo), indexar, obra_repo


@pytest.mark.asyncio
async def test_el_operador_promueve_a_norma_y_queda_pendiente_con_origen():
    uc, indexar, obra_repo = _promotor(_obra())

    await uc.ejecutar(
        obra_id=5,
        usuario_id=10,
        es_supervisor=False,
        nombre="Ley de recursos",
        jerarquia="supletoria",
    )

    req = indexar.ejecutar.await_args.args[0]
    assert (req.categoria, req.estado_visibilidad, req.origen_obra_id) == ("norma", "pendiente", 5)
    assert (req.nombre, req.jerarquia, req.propietario_id) == ("Ley de recursos", "supletoria", 10)
    assert req.texto_directo.startswith("Artículo 1")
    obra_repo.marcar_promocion.assert_awaited_once_with(5, "promovida_a_norma")


@pytest.mark.asyncio
async def test_el_supervisor_promueve_directo_a_global():
    uc, indexar, _ = _promotor(_obra(propietario_id=99))

    await uc.ejecutar(
        obra_id=5, usuario_id=20, es_supervisor=True, nombre="Ley X", jerarquia="suprema"
    )

    assert indexar.ejecutar.await_args.args[0].estado_visibilidad == "global"


@pytest.mark.asyncio
async def test_solo_el_dueno_promueve_a_norma_si_no_es_supervisor():
    uc, _, _ = _promotor(_obra(propietario_id=99))

    with pytest.raises(FuenteNoPropiaError):
        await uc.ejecutar(
            obra_id=5, usuario_id=10, es_supervisor=False, nombre="Ley", jerarquia="militar"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cambios",
    [
        {"estado_visibilidad": "privado"},
        {"tipo_documento": "doctrina"},
        {"estado_validacion": "promovida_a_norma"},
        {"contenido_texto": "   "},
    ],
)
async def test_no_se_promueve_a_norma_lo_que_no_es_promovible(cambios):
    uc, indexar, _ = _promotor(_obra(**cambios))

    with pytest.raises(TransicionInvalidaError):
        await uc.ejecutar(
            obra_id=5, usuario_id=10, es_supervisor=False, nombre="Ley", jerarquia="militar"
        )
    indexar.ejecutar.assert_not_awaited()


@pytest.mark.asyncio
async def test_obra_inexistente_al_promover_a_norma():
    uc, _, _ = _promotor(None)

    with pytest.raises(FuenteNoEncontradaError):
        await uc.ejecutar(
            obra_id=5, usuario_id=10, es_supervisor=False, nombre="Ley", jerarquia="militar"
        )
