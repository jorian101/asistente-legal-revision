"""Candado: ningún flujo N2/N3 toca criterios (RG3, replanteo punto 5).

Los criterios del vocal van por slot {{criterio_vocal}} propio; la
jurisprudencia (N2) y los libros (N3) jamás deben leerlos, copiarlos
ni recomendarlos. Si algún flujo futuro necesita nombrarlos, este test
obliga a actualizar la allowlist a conciencia.
"""

from __future__ import annotations

from pathlib import Path


def _raiz_src() -> Path:
    return Path(__file__).resolve().parents[2] / "src"


# Menciones conscientes y seguras (título de libro, docstrings de
# exclusión). Cualquier otra mención nueva falla el test a propósito.
_PERMITIDAS: tuple[tuple[str, str], ...] = (
    ("domain/services/segmentacion/doctrina.py", "criterios de evaluación"),
    (
        "application/doctrina/seleccionar_corpus.py",
        "No toca criterios ni el flujo de copia",
    ),
)


def test_flujos_n2_n3_no_mencionan_criterio() -> None:
    """Barrido estático: cero menciones a 'criterio' en módulos N2/N3."""
    archivos = [
        "domain/services/segmentacion/scp.py",
        "domain/services/segmentacion/cidh.py",
        "domain/services/segmentacion/doctrina.py",
        "adapters/qdrant/qdrant_jurisprudencia_repo.py",
        "adapters/qdrant/qdrant_doctrina_repo.py",
        "application/doctrina/seleccionar_corpus.py",
        "application/corpus/listar_corpus_por_jerarquia.py",
    ]
    raiz = _raiz_src()
    menciones: list[str] = []
    for rel in archivos:
        texto = (raiz / rel).read_text(encoding="utf-8")
        for i, linea in enumerate(texto.split("\n"), start=1):
            if "criterio" in linea.lower() and not any(
                r == rel and p in linea for r, p in _PERMITIDAS
            ):
                menciones.append(f"{rel}:{i}: {linea.strip()[:80]}")
    assert menciones == [], f"Flujos N2/N3 no deben tocar criterios: {menciones}"


def test_tipo_documento_no_editable_por_api() -> None:
    """Nadie puede mutar tipo_documento (ej. memorial -> jurisprudencia).

    actualizar_detalles no acepta el campo: el tipo se fija en creación (upload o
    puntero) y solo cambia por la promoción aprobada (`promover_a_jurisprudencia`).
    """
    import inspect

    from src.adapters.postgres.repos.obra_repo import ObraRepoImpl

    params = inspect.signature(ObraRepoImpl.actualizar_detalles).parameters
    assert "tipo_documento" not in params
