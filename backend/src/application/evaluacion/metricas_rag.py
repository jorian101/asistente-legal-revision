"""Metricas deterministas de evaluacion RAG (DoD 3.4.8 — suite golden set).

Dominio puro: sin I/O, sin LLM, sin stack. Funciones sobre la forma
canonica de un resultado de recuperacion:

    recuperados: lista ordenada de ids de obra/fragmento (top-k, orden = ranking).
    esperados: conjunto de ids que DEBIAN recuperarse (del golden set).

Metricas:
- recall@k: fraccion de esperados presentes en los primeros k recuperados.
- precision@k: fraccion de los primeros k que son esperados.
- reciprocal_rank: 1/rango del primer esperado (0 si ninguno).
- mrr: promedio de reciprocal_rank sobre un lote de casos.

Skill evaluation: checks deterministas antes de cualquier LLM-judge;
un solo numero no basta — se reporta el triple (recall, precision, MRR).
"""

from __future__ import annotations


def recall_at_k(recuperados: list[int], esperados: set[int], k: int) -> float:
    """Recall@k: que fraccion de los esperados aparece en el top-k.

    Caso borde: esperados vacio -> 1.0 (nada que recuperar, no penaliza).
    """
    if k < 1:
        raise ValueError("k debe ser >= 1")
    if not esperados:
        return 1.0
    top = set(recuperados[:k])
    return len(top & esperados) / len(esperados)


def precision_at_k(recuperados: list[int], esperados: set[int], k: int) -> float:
    """Precision@k: que fraccion del top-k es relevante.

    Caso borde: top-k vacio (nada recuperado) -> 0.0.
    """
    if k < 1:
        raise ValueError("k debe ser >= 1")
    top = recuperados[:k]
    if not top:
        return 0.0
    return len(set(top) & esperados) / len(top)


def reciprocal_rank(recuperados: list[int], esperados: set[int]) -> float:
    """1/rango (1-indexed) del primer recuperado que sea esperado. 0 si ninguno."""
    for rango, oid in enumerate(recuperados, start=1):
        if oid in esperados:
            return 1.0 / rango
    return 0.0


def mrr(casos: list[tuple[list[int], set[int]]]) -> float:
    """Mean Reciprocal Rank sobre un lote de casos (recuperados, esperados)."""
    if not casos:
        return 0.0
    return sum(reciprocal_rank(rec, esp) for rec, esp in casos) / len(casos)


def resumen(casos: list[tuple[list[int], set[int]]], k: int) -> dict[str, float]:
    """Agrega las metricas sobre el lote: recall@k medio, precision@k medio y MRR."""
    if not casos:
        return {"recall_at_k": 0.0, "precision_at_k": 0.0, "mrr": 0.0, "n": 0.0}
    n = len(casos)
    return {
        "recall_at_k": sum(recall_at_k(r, e, k) for r, e in casos) / n,
        "precision_at_k": sum(precision_at_k(r, e, k) for r, e in casos) / n,
        "mrr": mrr(casos),
        "n": float(n),
    }


__all__ = ["mrr", "precision_at_k", "recall_at_k", "reciprocal_rank", "resumen"]
