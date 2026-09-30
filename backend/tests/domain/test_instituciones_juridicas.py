"""Tests: consultas dirigidas por institución jurídica o artículo explícito.

Bug: «dime sobre el articulo del debido proceso» no traía CPE 115 ni CPP 1
porque nada relacionaba la institución con su norma.
"""

from __future__ import annotations

import pytest

from src.domain.services.instituciones_juridicas import articulos_explicitos, consultas_dirigidas


def _refs(consulta: str) -> list[tuple[str, int | None]]:
    return [(f["abreviatura"], f.get("numero_articulo")) for _q, f in consultas_dirigidas(consulta)]


def test_debido_proceso_trae_cpe_y_cpp_supletorio():
    refs = _refs("debido proceso")

    assert ("CPE", 115) in refs
    assert ("CPE", 117) in refs
    assert ("CPP", 1) in refs


def test_cpe_va_antes_que_el_cpp_supletorio():
    refs = _refs("debido proceso")

    assert refs.index(("CPE", 115)) < refs.index(("CPP", 1))


def test_presuncion_de_inocencia_con_tilde_o_sin_ella():
    assert ("CPE", 116) in _refs("la presunción de inocencia")
    assert ("CPE", 116) in _refs("presuncion de inocencia")


@pytest.mark.parametrize(
    "consulta,esperado",
    [
        ("que dice el articulo 115 de la CPE", ("CPE", 115)),
        ("art. 63 de la LOJM", ("LOJM", 63)),
        ("artículo 133 del CPP", ("CPP", 133)),
        ("articulo 1 de la Ley 1970", ("CPP", 1)),
        ("artículo 180 de la Constitución", ("CPE", 180)),
        # exp-3349: el nombre completo de la norma también la resuelve.
        ("uso de documentos falsos articulo 178 del codigo penal militar", ("CPM", 178)),
        ("artículo 178 del Código Penal Militar", ("CPM", 178)),
        # Sigla pegada al número, como la escribe el criterio del vocal.
        ("**Art. 179.I CPE**: unidad de la función judicial", ("CPE", 179)),
        ("Art. 125 CPP (Ley 1970) como supletorio", ("CPP", 125)),
    ],
)
def test_articulo_explicito(consulta, esperado):
    assert esperado in _refs(consulta)


def test_consulta_sin_institucion_ni_articulo_no_agrega_nada():
    assert consultas_dirigidas("plazo para apelar una sentencia") == ()


def test_sin_duplicados():
    refs = _refs("debido proceso, articulo 115 de la CPE")

    assert len(refs) == len(set(refs))


def test_articulo_explicito_lleva_mas_peso_que_la_institucion():
    explicitas = dict(consultas_dirigidas("art. 115 de la CPE"))
    inst = dict(consultas_dirigidas("debido proceso"))

    peso_explicito = next(iter(explicitas.values()))["peso_rrf"]
    assert peso_explicito > 1
    assert all("peso_rrf" not in f for f in inst.values())


def test_articulos_explicitos_solo_trae_citas_escritas():
    """Para recuperar las normas del criterio: solo lo citado, no lo inferido por institución."""
    texto = "el debido proceso; Art. 410.II CPE y Art. 180.III CPE; de nuevo Art. 410.II CPE"

    assert articulos_explicitos(texto) == (("CPE", 410), ("CPE", 180))
