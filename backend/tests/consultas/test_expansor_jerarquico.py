"""Tests de ExpansorJerarquicoImpl — expansion jerarquica + Regla 6 (Sprint 5).

Fase 3.1: 4 tests. `test_regla6_end_to_end` es BLOQUEANTE.

Cubre:
- Regla 6 end-to-end: operador A no recibe fragmentos ascendidos de obra
  privada de operador B.
- Breadcrumbs: path ordenado raiz -> hijo usando padre_ref_key.
- top_k_padres_a_incluir limita la cantidad de padres.
- max_profundidad_bfs corta el BFS ascendente.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.expansor_jerarquico import ExpansorJerarquicoImpl
from src.domain.entities.configuracion_rag import ConfiguracionRAG
from src.domain.entities.fragmento import Fragmento
from src.domain.entities.obra import Obra
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado


def _frag(
    id: int,
    obra_id: int | None = None,
    norma_id: int | None = None,
    padre_ref_id: int | None = None,
    padre_ref_key: str | None = None,
    nivel: int | None = None,
    qdrant_id: str | None = None,
) -> Fragmento:
    """Factory de Fragmento para tests."""
    return Fragmento(
        id=id,
        norma_id=norma_id if norma_id is not None else (None if obra_id is not None else 1),
        obra_id=obra_id,
        expediente_id=None,
        qdrant_point_id=qdrant_id or f"qdrant-{id}",
        texto=f"texto fragmento {id}",
        padre_ref_id=padre_ref_id,
        padre_ref_key=padre_ref_key,
        nivel_jerarquico=nivel,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


def _obra(id: int, propietario_id: int, visibilidad: str = "privado") -> Obra:
    return Obra(
        id=id,
        expediente_id=1,
        propietario_id=propietario_id,
        tipo_documento="sentencia",
        nombre_archivo=f"obra-{id}.pdf",
        contenido_texto="...",
        ruta_archivo=None,
        fojas_inicio=None,
        fojas_fin=None,
        estado_visibilidad=visibilidad,
        fuente="carga_usuario",
        tamano_archivo=None,
        estado_procesamiento="completado",
        created_at=None,
    )


def _config(max_depth: int = 3, top_k_padres: int = 5) -> ConfiguracionRAG:
    return ConfiguracionRAG(
        id=1,
        score_threshold=0.5,
        top_k_denso=10,
        top_k_lexico=10,
        top_k_final=5,
        modelo_embeddings="all-MiniLM-L6-v2",
        modelo_llm_default="llama3.2",
        max_profundidad_bfs=max_depth,
        top_k_padres_a_incluir=top_k_padres,
    )


def _contexto_recuperado(
    fragmentos: tuple[Fragmento, ...],
    scores: tuple[float, ...],
) -> ContextoRecuperado:
    return ContextoRecuperado(
        fragmentos=fragmentos,
        scores=scores,
        query_original="que dice el art 184",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        latencia_ms=100,
    )


def _make_expansor(
    fragmento_repo: MagicMock,
    obra_repo: MagicMock,
    config_repo: MagicMock,
) -> ExpansorJerarquicoImpl:
    return ExpansorJerarquicoImpl(
        fragmento_repo=fragmento_repo,
        obra_repo=obra_repo,
        config_repo=config_repo,
    )


@pytest.mark.asyncio
async def test_regla6_end_to_end_opera_a_no_recibe_padres_de_obra_privada_de_b() -> None:
    """BLOQUEANTE. Operador A (usuario_id=1) consulta; obra 100 es privada
    de operador B (usuario_id=2). El padre ascendido de obra 100 NO aparece
    en el ContextoExpandido del operador A.

    Escenario:
    - Hijo 10 (obra 100, privada de B) -> padre 20 (obra 100, privada de B)
    - Hijo 30 (obra 200, propia de A) -> padre 40 (obra 200, propia de A)
    - Hijo 50 (norma_id=1, sin obra) -> padre 60 (norma_id=1, sin obra)

    Operador A (usuario_id=1) debe recibir:
    - Hijos: 30 (obra propia), 50 (norma, sin obra)
    - Padres: 40 (obra propia), 60 (norma, sin obra)
    - NO recibir: 10, 20 (obra privada ajena)
    """
    hijos = (
        _frag(id=10, obra_id=100, padre_ref_id=20, padre_ref_key="H10", nivel=4),
        _frag(id=30, obra_id=200, padre_ref_id=40, padre_ref_key="H30", nivel=4),
        _frag(id=50, obra_id=None, norma_id=1, padre_ref_id=60, padre_ref_key="H50", nivel=4),
    )
    padres_ascendidos = [
        _frag(id=20, obra_id=100, padre_ref_key="P20", nivel=3),
        _frag(id=40, obra_id=200, padre_ref_key="P40", nivel=3),
        _frag(id=60, obra_id=None, norma_id=1, padre_ref_key="P60", nivel=3),
    ]

    obras = {
        200: _obra(id=200, propietario_id=1, visibilidad="privado"),
    }
    # Nota: obra 100 es privada de B, NO aparece en el dict — esa ausencia
    # es la senal de poda para EvaluadorVisibilidad.

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=padres_ascendidos)

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value=obras)

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=3, top_k_padres=5))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(
        fragmentos=hijos,
        scores=(0.9, 0.8, 0.7),
    )

    resultado = await expansor.expandir(contexto=contexto, usuario_id=1)

    ids_expandidos = {f.id for f in resultado.fragmentos_con_padres}

    assert 10 not in ids_expandidos, "Regla 6: hijo de obra privada ajena podado"
    assert 20 not in ids_expandidos, "Regla 6: padre de obra privada ajena podado"
    assert 30 in ids_expandidos, "Hijo de obra propia (obra 200) debe estar"
    assert 40 in ids_expandidos, "Padre de obra propia (obra 200) debe estar"
    assert 50 in ids_expandidos, "Hijo de norma (sin obra) debe estar"
    assert 60 in ids_expandidos, "Padre de norma (sin obra) debe estar"
    assert resultado.trazabilidad is not None
    assert resultado.trazabilidad.expansion_realizada is True
    # 3 padres ascendidos, 1 podado por Regla 6 (padre 20 de obra privada ajena).
    assert resultado.trazabilidad.nodos_ascendidos == 2
    assert resultado.trazabilidad.fragmentos_originales_count == 3
    assert resultado.trazabilidad.fragmentos_expandidos_count == 4


@pytest.mark.asyncio
async def test_breadcrumbs_path_correcto_raiz_a_hijo() -> None:
    """Breadcrumb de un hijo a nivel 4 contiene padre_ref_key de niveles
    3, 2, 1 (raiz -> hijo).

    Jerarquia: 1 (raiz) -> 2 -> 3 -> 4 (hijo)
    padre_ref_keys: ROOT -> N2 -> N3 -> N4
    """
    hijo = _frag(id=4, obra_id=None, norma_id=1, padre_ref_id=3, padre_ref_key="N4", nivel=4)
    padre3 = _frag(id=3, obra_id=None, norma_id=1, padre_ref_id=2, padre_ref_key="N3", nivel=3)
    padre2 = _frag(id=2, obra_id=None, norma_id=1, padre_ref_id=1, padre_ref_key="N2", nivel=2)
    padre1 = _frag(id=1, obra_id=None, norma_id=1, padre_ref_id=None, padre_ref_key="ROOT", nivel=1)

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=[padre3, padre2, padre1])

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=3, top_k_padres=5))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(fragmentos=(hijo,), scores=(0.95,))

    resultado = await expansor.expandir(contexto=contexto, usuario_id=1)

    assert len(resultado.breadcrumbs) == 1
    breadcrumb = resultado.breadcrumbs[0]
    assert breadcrumb == ("ROOT", "N2", "N3", "N4"), f"Expected path raiz->hijo, got {breadcrumb}"


@pytest.mark.asyncio
async def test_top_k_padres_a_incluir_limita_cantidad_de_padres() -> None:
    """Si hay mas padres visibles que top_k_padres_a_incluir, se trunca."""
    hijos = (
        _frag(id=10, obra_id=None, norma_id=1, padre_ref_id=1, padre_ref_key="H10"),
        _frag(id=20, obra_id=None, norma_id=1, padre_ref_id=2, padre_ref_key="H20"),
        _frag(id=30, obra_id=None, norma_id=1, padre_ref_id=3, padre_ref_key="H30"),
    )
    padres = [
        _frag(id=1, obra_id=None, norma_id=1, padre_ref_key="P1"),
        _frag(id=2, obra_id=None, norma_id=1, padre_ref_key="P2"),
        _frag(id=3, obra_id=None, norma_id=1, padre_ref_key="P3"),
    ]

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=padres)

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=3, top_k_padres=2))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(fragmentos=hijos, scores=(0.9, 0.8, 0.7))

    resultado = await expansor.expandir(contexto=contexto, usuario_id=1)

    padres_en_resultado = [f for f in resultado.fragmentos_con_padres if f.id in {1, 2, 3}]
    assert len(padres_en_resultado) <= 2, f"top_k_padres=2, got {len(padres_en_resultado)}"
    assert resultado.trazabilidad.nodos_ascendidos <= 2


@pytest.mark.asyncio
async def test_max_profundidad_bfs_corta_el_ascenso() -> None:
    """max_profundidad_bfs=1: solo se asciende 1 nivel (los padres del hijo,
    pero no los abuelos).
    """
    hijo = _frag(id=10, obra_id=None, norma_id=1, padre_ref_id=5, padre_ref_key="H10", nivel=4)
    padre = _frag(id=5, obra_id=None, norma_id=1, padre_ref_id=1, padre_ref_key="P5", nivel=3)
    # El abuelo (id=1) NO deberia aparecer si max_depth=1.

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=[padre])

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=1, top_k_padres=5))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(fragmentos=(hijo,), scores=(0.9,))

    resultado = await expansor.expandir(contexto=contexto, usuario_id=1)

    ids_expandidos = {f.id for f in resultado.fragmentos_con_padres}
    assert 5 in ids_expandidos, "Padre inmediato debe estar"
    assert 1 not in ids_expandidos, "Abuelo no debe estar con max_depth=1"

    fragmento_repo.get_ascendencia.assert_awaited_once()
    call_kwargs = fragmento_repo.get_ascendencia.call_args
    assert call_kwargs.kwargs["max_depth"] == 1


@pytest.mark.asyncio
async def test_resolver_breadcrumbs_no_expande_solo_construye_ruta() -> None:
    """G6: resolver_breadcrumbs devuelve los MISMOS fragmentos + breadcrumbs.

    Escenario: hijo 10 (padre_ref_key='CPPM_184') con padre 20
    (padre_ref_key='CPPM_1_184'). Sin expansion: fragmentos_con_padres
    solo contiene el hijo (no los padres), breadcrumbs = ruta raiz->hijo.
    """
    padre = _frag(20, norma_id=1, padre_ref_id=None, padre_ref_key="CPPM_1_184", nivel=3)
    hijo = _frag(10, norma_id=1, padre_ref_id=20, padre_ref_key="CPPM_184", nivel=4)

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=[padre])

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=3, top_k_padres=5))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(fragmentos=(hijo,), scores=(0.9,))

    resultado = await expansor.resolver_breadcrumbs(contexto=contexto, usuario_id=1)

    # NO se expande: solo los hijos originales, sin padres añadidos
    assert len(resultado.fragmentos_con_padres) == 1
    assert resultado.fragmentos_con_padres[0].id == 10
    assert resultado.scores == (0.9,)
    # Breadcrumbs: ruta raiz -> hijo (padre, hijo)
    # Sanitizado: sin sufijos tecnicos ni guiones bajos (T0).
    assert resultado.breadcrumbs == (("CPPM 1 184", "CPPM 184"),)
    # Trazabilidad marca que NO hubo expansion completa
    assert resultado.trazabilidad is not None
    assert resultado.trazabilidad.expansion_realizada is False
    assert resultado.trazabilidad.breadcrumbs_count == 2


@pytest.mark.asyncio
async def test_resolver_breadcrumbs_poda_obra_privada_ajena() -> None:
    """G6 Regla 6: la ruta no refleja padres de obra privada ajena."""

    # Obra 100 es privada de B (propietario 2); hijo 10 y padre 20 son de esa obra
    padre = _frag(20, obra_id=100, padre_ref_id=None, padre_ref_key="OBRA_PRIVADA", nivel=3)
    hijo = _frag(10, obra_id=100, padre_ref_id=20, padre_ref_key="OBRA_PRIVADA_HIJO", nivel=4)

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=[padre])

    # Regla 5: el batch filtra la obra privada ajena -> dict vacio
    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config(max_depth=3, top_k_padres=5))

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)

    contexto = _contexto_recuperado(fragmentos=(hijo,), scores=(0.9,))

    resultado = await expansor.resolver_breadcrumbs(contexto=contexto, usuario_id=1)

    # La obra es privada ajena -> no hay ruta jerarquica visible
    assert resultado.breadcrumbs == (("OBRA PRIVADA",),)  # sufijo _HIJO sanitizado


def test_etiqueta_legible_quita_sufijos_tecnicos() -> None:
    from src.domain.services.referencias import etiqueta_legible

    assert etiqueta_legible("LOJM_3_MASTER") == "LOJM 3"
    assert etiqueta_legible("CPPM_184_HIJO") == "CPPM 184"
    # Claves simples quedan iguales (compat con tests existentes).
    assert etiqueta_legible("ROOT") == "ROOT"


@pytest.mark.asyncio
async def test_breadcrumbs_sin_uuid_cuando_falta_padre_ref_key() -> None:
    """Nodos sin padre_ref_key se omiten del path (no filtra qdrant UUID)."""
    hijo = _frag(id=10, obra_id=None, norma_id=1, padre_ref_id=None, padre_ref_key=None)

    fragmento_repo = MagicMock()
    fragmento_repo.get_ascendencia = AsyncMock(return_value=[])

    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(return_value={})

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(return_value=_config())

    expansor = _make_expansor(fragmento_repo, obra_repo, config_repo)
    contexto = _contexto_recuperado(fragmentos=(hijo,), scores=(0.9,))

    resultado = await expansor.expandir(contexto=contexto, usuario_id=1)

    assert resultado.breadcrumbs[0] == ()
