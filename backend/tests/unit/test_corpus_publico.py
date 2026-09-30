"""La guarda del paquete de corpus público: ningún obrado ni expediente sale de la BD."""

from __future__ import annotations

import pytest
from qdrant_client import models

from scripts.corpus_publico import (
    FugaDePrivadosError,
    _vector_a_json,
    _vector_de_json,
    validar_fragmentos,
    validar_punto,
)

NORMA_GLOBAL = {"norma_id": 7, "tipo_fuente": "norma", "abreviatura": "CPP"}


def test_acepta_fragmentos_y_puntos_de_normas_globales() -> None:
    validar_fragmentos([{"id": 1, "obra_id": None, "expediente_id": None}])
    validar_punto("corpus_juridico", NORMA_GLOBAL)
    validar_punto("doctrina", {**NORMA_GLOBAL, "visibilidad": "global", "propietario_id": 3})


@pytest.mark.parametrize("campo", ["obra_id", "expediente_id"])
def test_fragmento_de_obra_o_expediente_aborta(campo) -> None:
    with pytest.raises(FugaDePrivadosError):
        validar_fragmentos([{"id": 1, "obra_id": None, "expediente_id": None, campo: 5}])


@pytest.mark.parametrize(
    "payload",
    [
        {**NORMA_GLOBAL, "obra_id": 9},  # obrado inyectado
        {**NORMA_GLOBAL, "expediente_id": 2},
        {**NORMA_GLOBAL, "tipo_fuente": "obra"},
        {**NORMA_GLOBAL, "visibilidad": "privado"},  # libro privado de un usuario
        {**NORMA_GLOBAL, "visibilidad": "pendiente"},
        {"tipo_fuente": "jurisprudencia"},  # sin norma_id: no es del corpus de normas
    ],
)
def test_punto_privado_aborta(payload) -> None:
    with pytest.raises(FugaDePrivadosError):
        validar_punto("corpus_juridico", payload)


def test_vectores_denso_y_sparse_ida_y_vuelta() -> None:
    vector = {"": [0.1, 0.2], "text-sparse": models.SparseVector(indices=[3, 9], values=[1.0, 0.5])}

    vuelta = _vector_de_json(_vector_a_json(vector))

    assert vuelta[""] == [0.1, 0.2]
    assert vuelta["text-sparse"] == models.SparseVector(indices=[3, 9], values=[1.0, 0.5])
