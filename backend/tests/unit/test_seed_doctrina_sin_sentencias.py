"""El seed de doctrina no debe sembrar sentencias como obras `doctrina`.

Las SCP y la Corte IDH son jurisprudencia: viven como norma (scripts/
indexar_jurisprudencia.py). Sembrarlas también como obra las duplicaba en
Qdrant y las mostraba como doctrina/obrado.
"""

from __future__ import annotations

from scripts.seed_doctrina_vault import _DOCTRINA


def test_ninguna_ficha_es_una_sentencia():
    archivos = [f["archivo"] for f in _DOCTRINA]

    assert not [a for a in archivos if a.startswith(("scp-", "sc-", "corte-idh"))]
    assert "doctrina-apelacion-incidental.txt" in archivos  # doctrina real
