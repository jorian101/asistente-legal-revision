"""Tests de QueriesCompetencia (P3) — queries de competencia por tipo.

Cubre:
- auto_vista_consulta -> incluye la norma de competencia de la consulta
  (Art. 194 CPPM), corrigiendo G5.
- auto_vista_apelacion_incidental -> incluye CPM (prescripcion, especial)
  y LOJM (competencia SAC), corrigiendo G6.
- consulta_simple -> vacio (no genera borrador).
- Tipo desconocido -> KeyError defensivo.
"""

from __future__ import annotations

import pytest

from src.domain.services.queries_competencia import queries_competencia


def test_auto_vista_consulta_incluye_norma_competencia() -> None:
    """G5: la query de competencia de la consulta apunta al Art. 194 CPPM."""
    qs = queries_competencia("auto_vista_consulta")
    assert qs
    q194 = [entrada for entrada in qs if entrada[1].get("numero_articulo") == 194]
    assert q194, "debe incluir una query con filtro numero_articulo=194"
    q, filtros = q194[0]
    assert filtros["abreviatura"] == "CPPM"
    assert "consulta de oficio" in q.lower()


def test_auto_vista_apelacion_incluye_cpm_prescripcion() -> None:
    """G6: la apelacion recupera la norma ESPECIAL (CPM) y LOJM (competencia)."""
    qs = queries_competencia("auto_vista_apelacion_incidental")
    filtros_cpm = [f for _, f in qs if f.get("abreviatura") == "CPM"]
    assert filtros_cpm, "debe incluir query con filtro abreviatura=CPM (norma especial)"
    assert "LOJM" in {f.get("abreviatura") for _, f in qs}


def test_consulta_simple_vacio() -> None:
    """consulta_simple no requiere competencia (no genera borrador)."""
    assert queries_competencia("consulta_simple") == ()


def test_tipo_desconocido_levanta_keyerror() -> None:
    """Defensa: tipo no mapeado -> KeyError (no silencio)."""
    with pytest.raises(KeyError):
        queries_competencia("tipo_invalido")  # type: ignore[arg-type]
