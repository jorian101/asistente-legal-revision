"""Test del filtro Qdrant por obras seleccionadas (obra_ids).

Verifica que `_apply_required_filters` incluye un MatchAny sobre `obra_id`
cuando se pasan obra_ids, respetando expediente_id y la privacidad (Regla 5).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo


def _repo() -> QdrantCorpusRepo:
    repo = QdrantCorpusRepo.__new__(QdrantCorpusRepo)  # sin conexion
    repo._client = MagicMock()
    repo._collection_name = "corpus_juridico"
    return repo


@pytest.mark.parametrize(
    "obra_ids,expediente_id",
    [
        ([1, 2, 3], 7),
        ([1], None),
        (None, 7),
    ],
)
def test_filtro_obra_ids(obra_ids, expediente_id):
    repo = _repo()

    filtros: dict = {"usuario_id": 5}
    if expediente_id is not None:
        filtros["expediente_id"] = expediente_id
    if obra_ids is not None:
        filtros["obra_ids"] = obra_ids

    filtro = repo._apply_required_filters(filtros, usuario_id=5)

    # Must contiene MatchAny sobre obra_id solo si se pasaron obras.
    condiciones_obra = [
        c
        for c in (filtro.must or [])
        if isinstance(c, models.FieldCondition) and c.key == "obra_id"
    ]
    if obra_ids:
        assert len(condiciones_obra) == 1
        assert condiciones_obra[0].match.any == obra_ids
    else:
        assert condiciones_obra == []

    # Expediente se mantiene como sub-filtro OR (expediente_id=X o IS NULL)
    # para incluir doctrina global (Plan C C1.2).
    if expediente_id is not None:
        sub_filtros = [c for c in (filtro.must or []) if isinstance(c, models.Filter)]
        assert sub_filtros, "debe existir sub-filtro de expediente_id"
        should = sub_filtros[0].should
        assert any(
            isinstance(c, models.FieldCondition)
            and c.key == "expediente_id"
            and c.match.value == expediente_id
            for c in should
        )

    # Privacidad (Regla 4) siempre presente.
    assert filtro.should


def test_filtro_obra_ids_vacio_ignora():
    repo = _repo()
    filtro = repo._apply_required_filters({"usuario_id": 5, "obra_ids": []}, usuario_id=5)
    condiciones_obra = [
        c
        for c in (filtro.must or [])
        if isinstance(c, models.FieldCondition) and c.key == "obra_id"
    ]
    assert condiciones_obra == []


def test_filtro_obra_ids_invalidos_raise():
    repo = _repo()
    with pytest.raises(ValueError):
        repo._apply_required_filters({"usuario_id": 5, "obra_ids": ["no-numero"]}, usuario_id=5)


def test_excluye_criterio_del_vocal():
    """Los criterios del Vocal nunca deben salir citados como fuente RAG.

    Se inyectan al prompt via {{criterio_vocal}}, no son jurisprudencia. El
    filtro Qdrant debe llevar must_not(tipo_documento=criterio) en toda busca.
    """
    repo = _repo()
    for filtros in ({"usuario_id": 5}, {"usuario_id": 5, "expediente_id": 8}):
        filtro = repo._apply_required_filters(filtros, usuario_id=5)
        assert filtro.must_not, "debe excluir algo por defecto"
        criterio = [
            c
            for c in filtro.must_not
            if isinstance(c, models.FieldCondition)
            and c.key == "tipo_documento"
            and c.match.value == "criterio"
        ]
        assert len(criterio) == 1, "must_not debe excluir tipo_documento=criterio"


def test_filtro_numero_articulo_se_aplica():
    """Las queries de competencia piden (abreviatura, numero_articulo): si el
    filtro ignora numero_articulo, se recupera cualquier articulo de la norma."""
    repo = _repo()

    filtro = repo._apply_required_filters(
        {"abreviatura": "LOJM", "numero_articulo": 63}, usuario_id=5
    )

    condiciones = [
        c
        for c in (filtro.must or [])
        if isinstance(c, models.FieldCondition) and c.key == "numero_articulo"
    ]
    assert len(condiciones) == 1
    assert condiciones[0].match.value == 63


def test_filtro_numero_articulo_invalido_lanza_error():
    with pytest.raises(ValueError):
        _repo()._apply_required_filters({"numero_articulo": "abc"}, usuario_id=5)
