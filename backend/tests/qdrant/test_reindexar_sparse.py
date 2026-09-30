"""scripts/reindexar_sparse.py recalcula el vector lexico de los puntos ya indexados.

`compute_bm25_sparse` cambio (tildes, palabras vacias, normalizacion): los vectores
guardados en Qdrant quedan obsoletos. El script los recalcula desde `payload["texto"]`
sin volver a embeber.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.reindexar_sparse import recalcular_sparse
from src.application.services.hybrid_searcher import compute_bm25_sparse


def _punto(pid: str, texto: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=pid, payload={"texto": texto} if texto is not None else {})


def _cliente(paginas: list[list[SimpleNamespace]]) -> MagicMock:
    client = MagicMock()
    siguientes = [f"off{i}" for i in range(len(paginas) - 1)] + [None]
    client.scroll.side_effect = list(zip(paginas, siguientes, strict=True))
    return client


def test_actualiza_el_sparse_de_cada_punto_con_texto_y_omite_los_demas() -> None:
    client = _cliente(
        [[_punto("a", "La detención preventiva"), _punto("b", None)], [_punto("c", "Cosa juzgada")]]
    )

    n = recalcular_sparse(client, "corpus_juridico", aplicar=True, lote=10)

    assert n == 2
    enviados = [p for c in client.update_vectors.call_args_list for p in c.kwargs["points"]]
    assert [p.id for p in enviados] == ["a", "c"]
    esperado = compute_bm25_sparse("La detención preventiva")
    sparse = enviados[0].vector["text-sparse"]
    assert list(sparse.indices) == list(esperado.indices)
    assert list(sparse.values) == list(esperado.values)


def test_sin_aplicar_no_escribe_nada() -> None:
    client = _cliente([[_punto("a", "texto")]])

    n = recalcular_sparse(client, "corpus_juridico", aplicar=False)

    assert n == 1
    client.update_vectors.assert_not_called()


def test_envia_los_puntos_en_lotes() -> None:
    client = _cliente([[_punto(str(i), f"texto {i}") for i in range(5)]])

    recalcular_sparse(client, "corpus_juridico", aplicar=True, lote=2)

    assert [len(c.kwargs["points"]) for c in client.update_vectors.call_args_list] == [2, 2, 1]
