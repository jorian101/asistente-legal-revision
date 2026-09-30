"""La migracion de creacion no borra la coleccion sin permiso explicito (F-32).

Ante un desajuste de dimension llamaba a delete_collection sin mirar
SAFETY_ALLOW_COLLECTION_RECREATE (que el adapter si respeta) ni respaldar: cambiar
EMBEDDING_DIM y ejecutar el script borraba todo el corpus, incluidas las obras
privadas indexadas.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from qdrant_migrations import create_corpus_juridico_collection as migracion

MODULO = "qdrant_migrations.create_corpus_juridico_collection"


def _cliente(dim_actual: int | None) -> MagicMock:
    cliente = MagicMock()
    existentes = [] if dim_actual is None else [SimpleNamespace(name=migracion.COLLECTION_NAME)]
    cliente.get_collections.return_value = SimpleNamespace(collections=existentes)
    if dim_actual is not None:
        info = SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=dim_actual)))
        )
        cliente.get_collection.return_value = info
    return cliente


def _ejecutar(cliente: MagicMock, *, dim_deseada: int, permite_recrear: bool) -> None:
    ajustes = SimpleNamespace(
        embedding_dim=dim_deseada,
        qdrant_url="http://qdrant:6333",
        qdrant_api_key=None,
        safety_allow_collection_recreate=permite_recrear,
    )
    with (
        patch(f"{MODULO}.QdrantClient", return_value=cliente),
        patch(f"{MODULO}.get_settings", return_value=ajustes),
    ):
        migracion.create_collection()


def test_desajuste_de_dimension_sin_permiso_no_borra_nada() -> None:
    cliente = _cliente(dim_actual=768)

    with pytest.raises(RuntimeError, match="SAFETY_ALLOW_COLLECTION_RECREATE"):
        _ejecutar(cliente, dim_deseada=1024, permite_recrear=False)

    cliente.delete_collection.assert_not_called()
    cliente.create_collection.assert_not_called()


def test_con_permiso_respalda_antes_de_borrar_y_recrea() -> None:
    cliente = _cliente(dim_actual=768)

    _ejecutar(cliente, dim_deseada=1024, permite_recrear=True)

    orden = [
        c[0]
        for c in cliente.method_calls
        if c[0] in ("create_snapshot", "delete_collection", "create_collection")
    ]
    assert orden == ["create_snapshot", "delete_collection", "create_collection"]


def test_misma_dimension_no_toca_la_coleccion() -> None:
    cliente = _cliente(dim_actual=768)

    _ejecutar(cliente, dim_deseada=768, permite_recrear=False)

    cliente.delete_collection.assert_not_called()
    cliente.create_collection.assert_not_called()


def test_si_no_existe_la_crea() -> None:
    cliente = _cliente(dim_actual=None)

    _ejecutar(cliente, dim_deseada=768, permite_recrear=False)

    cliente.create_collection.assert_called_once()
    cliente.delete_collection.assert_not_called()


def test_la_coleccion_nueva_lleva_sparse_e_indices_de_privacidad() -> None:
    """Sin `text-sparse` ni indices de payload la busqueda hibrida degradaba a densa y los
    filtros de privacidad (visibilidad, propietario_id) iban sin indice (R4)."""
    cliente = _cliente(dim_actual=None)

    _ejecutar(cliente, dim_deseada=768, permite_recrear=False)

    kwargs = cliente.create_collection.call_args.kwargs
    assert "text-sparse" in kwargs["sparse_vectors_config"]
    campos = {c.kwargs["field_name"] for c in cliente.create_payload_index.call_args_list}
    assert {"visibilidad", "propietario_id", "obra_id", "expediente_id"} <= campos
