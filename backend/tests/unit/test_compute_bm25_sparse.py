"""Tests de compute_bm25_sparse (canal léxico del HybridSearcher).

Qdrant valida que los sparse indices sean únicos: tokens repetidos deben
agregarse como term frequency, no duplicar el índice (422 en upsert/query).
"""

from __future__ import annotations

from src.application.services.hybrid_searcher import compute_bm25_sparse


def test_indices_unicos_con_tokens_repetidos() -> None:
    sv = compute_bm25_sparse("delito delito delito sentencia")

    assert len(sv.indices) == len(set(sv.indices)), "indices duplicados"


def test_repetir_un_token_pesa_mas_pero_no_linealmente() -> None:
    sv = compute_bm25_sparse("delito delito delito sentencia")

    por_indice = dict(zip(sv.indices, sv.values, strict=True))
    repetido, unico = sorted(por_indice.values(), reverse=True)
    assert repetido > unico > 0
    assert repetido / unico < 3  # tf sublineal (1 + ln tf), no proporcional a 3


def test_deterministico_y_case_insensitive() -> None:
    a = compute_bm25_sparse("Abandono de Servicio")
    b = compute_bm25_sparse("abandono de servicio")

    assert a.indices == b.indices
    assert a.values == b.values


def test_texto_vacio_devuelve_vector_vacio() -> None:
    sv = compute_bm25_sparse("")

    assert sv.indices == ()
    assert sv.values == ()


def _dot(a, b) -> float:
    pa = dict(zip(a.indices, a.values, strict=True))
    return sum(v * pa.get(i, 0.0) for i, v in zip(b.indices, b.values, strict=True))


def test_las_tildes_no_parten_las_palabras() -> None:
    """`[a-z0-9]+` sobre 'detención' daba 'detenci' + 'n': nunca casaba palabras con tilde."""
    assert len(compute_bm25_sparse("detención").indices) == 1
    assert compute_bm25_sparse("detención").indices == compute_bm25_sparse("DETENCION").indices


def test_las_palabras_vacias_no_puntuan() -> None:
    assert compute_bm25_sparse("de la que el los").indices == ()


def test_un_fragmento_largo_no_gana_solo_por_ser_largo() -> None:
    """Sin normalizar por longitud, el fragmento más largo ganaba cualquier consulta (hub)."""
    consulta = compute_bm25_sparse("detención preventiva")
    corto = compute_bm25_sparse("La detención preventiva cesará cuando desaparezcan los motivos")
    largo = compute_bm25_sparse(
        "detención preventiva " + " ".join(f"palabra{i} otra{i} cosa{i}" for i in range(150))
    )

    assert _dot(corto, consulta) > _dot(largo, consulta)
